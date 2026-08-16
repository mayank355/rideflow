# RideFlow — Scaling Analysis

What breaks first as RideFlow grows from its current single-instance, low-traffic state to 10x and 100x the number of drivers/riders, and what the fix looks like at each stage.

---

## Baseline: What RideFlow Runs Today

- One FastAPI app instance (single container)
- One Postgres instance (no read replicas)
- One Redis instance (no cluster)
- WebSocket connections held in-process, in-memory
- No load balancer — one instance serves 100% of traffic

This is correct and appropriate at current scale. Everything below identifies exactly where each assumption stops holding.

---

## 1. Redis GEOSEARCH — the first real bottleneck

**What works today:** all driver locations live in one Redis key (`driver_locations`), and `GEOSEARCH` does an indexed radius query against it. At hundreds or low thousands of drivers, this is fast — sub-millisecond.

**What breaks at 10x-100x:** a single Redis instance is single-threaded for command execution. As driver count grows into the tens of thousands, and especially as write frequency scales (every driver pinging every 2-5 seconds), two pressures compound:
- **Write throughput**: thousands of `GEOADD` calls per second start to queue behind each other on one instance.
- **Query cost at high density**: `GEOSEARCH` over a very large member count in a dense city (e.g. all of Mumbai's drivers in one geospatial set) becomes a heavier scan, even though it's indexed — radius queries in crowded areas return more candidates to rank.

**The fix, in stages:**
- **10x**: Redis can handle this on a single, appropriately-sized instance — vertical scaling (more CPU/RAM) buys real headroom before any architectural change is needed.
- **100x**: move to **Redis Cluster**, sharding driver locations by geography — e.g. one shard per city or one shard per geohash prefix range. This keeps `GEOSEARCH` queries local to a shard (a rider in Delhi never needs to query a shard holding Mumbai's drivers), avoiding cross-shard fan-out for the common case.
- **Beyond Redis geospatial entirely**: at true Uber-scale, companies move to custom geo-indexing (H3 hexagonal cells) with a purpose-built service layer, since generic Redis geo-commands aren't optimized for the specific access patterns (nearest-K, not just radius) real dispatch systems need.

**Interview line:** *"Redis GEOSEARCH is genuinely fast at our current scale, but it's a single-instance, single-threaded bottleneck at high write volume. I'd shard by geography in Redis Cluster before considering a custom indexing layer — sharding by city means most queries never cross shard boundaries, since a rider only ever searches near their own location."*

---

## 2. Postgres Connection Pooling

**What works today:** each request opens a SQLAlchemy session via `get_db()`, borrowed from a small default connection pool, closed when the request ends. At low request volume this is invisible.

**What breaks at 10x-100x:** Postgres has a hard cap on total concurrent connections (commonly ~100-300 depending on configuration). If the app scales to multiple instances (see #4 below) without a shared connection pooling layer, each instance maintains its *own* pool — 10 app instances x 20 connections each = 200 connections, potentially exhausting Postgres's limit before any single instance is even under heavy individual load.

**The fix:**
- Introduce **PgBouncer** (or Railway/managed-Postgres's built-in pooler) as a connection multiplexer sitting between the app instances and Postgres — many app-level "connections" share a smaller number of actual Postgres connections, since most connections spend most of their time idle between queries.
- Tune SQLAlchemy's own pool size (`pool_size`, `max_overflow`) deliberately per instance, rather than relying on defaults, once the instance count is known.
- **Read replicas**: once read-heavy endpoints (trip history, route lookup) meaningfully compete with write-heavy ones (location-triggered inserts, trip creation) for connection slots, route read-only queries to a replica, keeping the primary free for writes.

**Interview line:** *"A single instance never hits Postgres's connection ceiling, but the moment you horizontally scale the app tier, connection count multiplies across instances — PgBouncer solves this by pooling at the proxy layer instead of the app layer, so ten app instances don't need ten times the actual database connections."*

---

## 3. WebSocket Connections Per Instance

**This is the limitation already known and documented since Phase 3** — restated here with actual scaling numbers.

**What works today:** the `ConnectionManager` is an in-memory Python dictionary living inside one process. A single instance can realistically hold tens of thousands of concurrent WebSocket connections before memory/file-descriptor limits become a concern — plenty for 10x current scale.

**What breaks at 100x:** the moment traffic requires *multiple* app instances behind a load balancer (which becomes necessary once a single instance's CPU/memory is saturated by request volume, independent of WebSocket count), a connection registered on instance A is completely invisible to instance B. A `POST /rides/request` landing on instance B has no way to push to a driver whose WebSocket happens to be held by instance A.

**The fix:** **Redis Pub/Sub** as a cross-instance message bus. Every app instance subscribes to a shared channel (or per-user channels). When any instance needs to push to a user, it publishes the event to Redis instead of trying to reach the connection directly; whichever instance actually holds that user's WebSocket picks up the published message from its subscription and forwards it down the socket it owns. This decouples "which instance generated this event" from "which instance can deliver it."

**Interview line:** *"WebSocket connections are inherently pinned to whichever process accepted them — that's true regardless of framework or language. The standard fix is a pub/sub layer so any instance can broadcast 'deliver this to user X' and the instance actually holding that connection picks it up. I didn't build this yet because it's only necessary once you're running multiple app instances, which single-instance RideFlow doesn't need today."*

---

## 4. Horizontal Scaling of the App Tier Itself

**What works today:** one FastAPI container handles all HTTP and WebSocket traffic.

**What breaks at 10x-100x:** CPU-bound work (JSON serialization, password hashing via bcrypt — deliberately slow by design, geospatial calculations) and sheer request volume eventually saturate a single instance's throughput, independent of database/Redis capacity.

**The fix:**
- Run multiple app instances behind a load balancer (Railway, or any cloud provider, supports this natively).
- **This is the exact point where #2 (connection pooling) and #3 (WebSocket pub/sub) stop being optional** — both problems only manifest once this step happens. They're prerequisites to horizontal scaling, not independent nice-to-haves.
- Stateless HTTP endpoints (registration, ride requests, status updates) scale trivially across instances since they don't hold any in-memory state between requests — the database is the only shared state, which is exactly why #2 matters.

**Interview line:** *"The app itself is mostly stateless and scales horizontally for free — the two things that DON'T scale for free the moment you add instances are the WebSocket connection registry and the database connection count, which is why those two problems are the ones that actually gate horizontal scaling, not CPU or request throughput directly."*

---

## 5. The Matching Engine's Sequential Postgres Lookup

**Already flagged honestly in Phase 2** — restated with scaling context.

**What works today:** `find_best_available_driver` queries Postgres once per Redis candidate, in a loop, to preserve distance ordering while filtering for availability. Fine when `GEOSEARCH` returns a handful of nearby candidates.

**What breaks at 100x:** in extremely dense areas (a stadium letting out, a major event), the candidate list from `GEOSEARCH` could genuinely be large — dozens of drivers within a small radius. A sequential per-candidate query starts to add real latency to the matching path, which is the single most latency-sensitive operation in the whole system (a rider is actively waiting for this response).

**The fix:** batch-fetch all candidates in one `WHERE id IN (...)` query, then re-sort in application code using the original Redis distance order (which is cheap — sorting a small in-memory list by a value you already have is negligible compared to N separate round-trips to the database).

**Interview line:** *"At high candidate density, I'd switch the matching loop to a single batched IN query instead of N sequential ones, re-sorting by the distance order GEOSEARCH already gave me. This trades a small amount of in-memory sorting for eliminating N-1 network round-trips to Postgres on the most latency-sensitive path in the system."*

---

## 6. Location Write Volume at Scale (Revisiting Phase 0's Core Lesson)

**What works today:** driver locations write to Redis, not Postgres, specifically to avoid the write-amplification problem established in Phase 0 (MVCC row versioning, WAL overhead, vacuum pressure from repeated updates to the same logical row).

**What still holds at 100x:** this design decision doesn't need to change — it scales precisely because Redis was chosen for exactly this access pattern. The scaling pressure at high driver count is on Redis's *sharding* (#1 above), not on the fundamental hot/cold split, which remains correct at any scale.

**Worth stating explicitly:** this is a case where the *original* architectural decision (Phase 0) doesn't need revisiting under scale — only its *implementation* (single Redis instance to Redis Cluster) needs to evolve. Good architecture decisions often look like this: the boundary was drawn correctly the first time, and scaling means reinforcing that boundary, not redrawing it.

---

## Summary Table

| Component | Breaks at | Fix |
|---|---|---|
| Redis GEOSEARCH | ~100x, dense cities | Redis Cluster, geo-sharded |
| Postgres connections | Multi-instance app tier | PgBouncer + read replicas |
| WebSocket registry | Multi-instance app tier | Redis Pub/Sub fanout |
| App tier CPU/throughput | ~10x request volume | Horizontal scaling + load balancer |
| Matching engine's N queries | High candidate density (events, dense areas) | Batch IN query + in-memory re-sort |
| Location write pattern | Never — correct design, only implementation scales | Redis Cluster sharding (same as #1) |

---

## What This Document Is For

This isn't a promise to build all of the above — it's proof of understanding *where* the current architecture's limits actually are, stated honestly, with the standard, real-world fix named for each. In an interview, the goal isn't claiming RideFlow is infinitely scalable as-is; it's demonstrating the ability to reason precisely about where a specific design choice stops holding and what replaces it — which is the actual skill being evaluated.
