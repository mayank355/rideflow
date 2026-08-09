What Phase 1 Actually Was

Built the first real feature slice: a driver can register (durable identity, written to Postgres) and report their live location (ephemeral, written to Redis via GEOADD). This is the first place the "hot path / cold path" split from Phase 0 became actual working code instead of just a diagram.

The Real-World Analogy (use this in interviews to frame the design)

A security guard's register book at a gate = permanent record of who a visitor is, written once, in ink, never erased. The guard's walkie-talkie chatter ("Guard 3, now at Block C") = constant, ephemeral updates with no long-term memory — if the next update doesn't come, you just have a stale "last known position," not a missing record.

Postgres drivers table = the register book (identity, rarely changes)
Redis GEOADD structure = the walkie-talkie (location, changes every few seconds, no history kept)
Core Concepts — Interview Ready
1. Why the Driver model has NO lat/lng columns
Identity fields (name, phone, vehicle) belong in Postgres — written once, read often, must never be lost.
Location changes every 2-5 seconds. Storing it as a Postgres column would mean constant UPDATE statements — reintroducing the exact write-amplification problem (MVCC row versioning + WAL logging + index maintenance) discussed in Phase 0.
Interview line: "The Driver model deliberately has no location columns — location is a different access pattern (high-frequency, low-durability) and lives entirely in Redis."
2. UUID primary keys instead of auto-increment integers
What it solves: auto-increment IDs (/drivers/1, /drivers/2) leak how many drivers exist and are trivially enumerable — a security concern.
At scale: if the Postgres database is ever sharded across multiple machines, auto-increment sequences generated independently on different shards can collide. UUIDs are globally unique without any central coordinator.
Interview line: "I used UUIDs because they're globally unique without needing coordination — which matters the moment you shard the database."
Tradeoff (one sentence): UUIDs are larger (16 bytes vs 4-8) and slightly slower to index than sequential integers — a real cost paid for global uniqueness and non-enumerability.
3. is_available status lives in Postgres, NOT Redis
Availability changes a few times per session (driver goes online/offline, gets assigned a trip) — low frequency enough that Postgres's write cost is acceptable.
Location changes every few seconds — too frequent for Postgres, hence Redis.
Interview line: "Not everything about a driver that changes belongs in Redis — only the sub-second-frequency data does. Status changes a few times an hour; that's fine in a relational table."
4. Redis GEOADD — the actual mechanism
Redis's geospatial commands are built on top of sorted sets. Normally a sorted set ranks members by a numeric score (leaderboard-style). Geospatial commands encode a lat/lng pair into a single number (a geohash) and use that as the score.
All drivers live under one single Redis key (driver_locations) as members of one geospatial structure — not one key per driver. This is what makes a future "find nearest driver" query (GEOSEARCH) fast: it searches across every driver in one command, because they're all in the same structure.
Critical gotcha: GEOADD key longitude latitude member — longitude comes first, not latitude. This is backwards from how people normally say "lat, long" in conversation. Getting it backwards silently puts a driver in the wrong hemisphere — no error is thrown.
Calling GEOADD again for the same driver_id overwrites their previous position. No history is kept — by design.
5. Why Postgres is still queried (read-only) during the location-update call
The endpoint checks db.query(Driver).filter(Driver.id == driver_id).first() before writing to Redis.
This is a cheap, indexed SELECT — confirming the driver_id is a real, registered driver — not a write. It doesn't reintroduce the write-amplification problem because nothing is being updated in Postgres.
Interview line: "Postgres is still in the loop for validation, but only as a read — the actual location write goes exclusively to Redis."
6. Pydantic field validation at the boundary
LocationUpdate schema uses Field(..., ge=-90, le=90) for latitude and ge=-180, le=180 for longitude — rejecting invalid coordinates before they ever reach business logic or Redis.
General principle: validate at the boundary (the schema/API layer), trust the data everywhere after that — don't scatter validation checks through business logic.
7. The get_db() dependency pattern (FastAPI + SQLAlchemy)
A generator function (yield instead of return) injected into routes via Depends(get_db).
The try/finally around the yield guarantees the database session is closed even if the route raises an exception mid-request.
Why it matters: without this, a crashing request would leak an open DB connection every time — under load, this exhausts the connection pool and takes down the whole service. This is a real production failure pattern, not a theoretical one.
8. create_all() vs Alembic — a decision explicitly deferred, not ignored
Base.metadata.create_all() creates tables that don't exist yet — fine for adding new tables from scratch (like drivers in this phase).
It does not handle altering an existing table (adding/removing/renaming columns) without data loss risk. The moment we need to change the drivers table's shape without dropping it, we switch to Alembic migrations.
Interview line: "I used create_all for initial schema setup since it's a new table with no data yet — but any schema change on a live table goes through Alembic migrations instead, since create_all can't safely alter existing structures."
One-Line Tradeoffs (memorize these)
UUID vs auto-increment: gain global uniqueness + no enumeration, lose compact size/index speed.
Redis GEOADD for location vs Postgres column: gain fast high-frequency writes with no durability guarantee, lose queryability via SQL and any location history.
create_all() vs Alembic: gain simplicity for a brand-new schema, lose safe schema evolution on live data — hence why this is a temporary choice, not a permanent one.
What to Say If Asked "Walk Me Through Driver Location Tracking" in an Interview

"A driver's identity — name, vehicle, phone — is a durable record in Postgres, written once at registration. Their live location is a completely separate concern: it changes every few seconds, so I store it in Redis using GEOADD, which encodes lat/long into a geospatial sorted set. All drivers share one Redis key, so a future nearest-driver search can scan everyone in a single GEOSEARCH call. The location-update endpoint does a cheap read against Postgres just to confirm the driver is registered, but the actual position write goes exclusively to Redis — Postgres never sees a location value, ever."

Diagnostic Pattern Reinforced This Phase

Same as Phase 0's "check status, then check logs" — extended here to code-level reasoning: before writing to a fast-changing store (Redis), always ask "does this identity actually exist in the source of truth (Postgres) first?" — cheap reads gate expensive/fast writes, rather than trusting an unvalidated ID blindly.