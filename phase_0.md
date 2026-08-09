What Phase 0 Actually Was

Not code — infrastructure. Got three containers (FastAPI app, PostgreSQL+PostGIS, Redis) running together, networked correctly, proven alive via a /health endpoint returning {"postgres":"connected","redis":"connected"}.

Core Concepts — Interview Ready
1. Why two databases (Postgres + Redis)?
Postgres = durable, relational, ACID — for data that must never disappear (trips, users, fares).
Redis = in-memory, fast, ephemeral — for data that's stale in seconds anyway (live driver location).
Interview line: "If losing the data for 5 seconds is fine, it goes in Redis. If losing it is never acceptable, it goes in Postgres."
Tradeoff: Redis gives speed + scale, sacrifices durability and queryability. Postgres gives consistency + relational integrity, sacrifices raw write throughput.
2. Why not just UPDATE driver location in Postgres every few seconds?
Mechanism (the actual answer, not just "it's slow"): Postgres uses MVCC — every UPDATE writes a new row version instead of overwriting in place, and logs the change to the WAL (write-ahead log) for durability. Thousands of drivers updating every 2-3 sec = massive dead tuple buildup → constant VACUUM overhead → index bloat → disk I/O saturation. This is called write amplification.
Redis just overwrites an in-memory key. No WAL, no dead tuples, no vacuum.
3. Why is it "safe" to lose Redis data?
Because it's self-healing — the driver's phone sends a fresh location update in the next few seconds regardless. You never need to recover a lost location; a new one is always coming.
Trip data has no such property — nobody automatically resends "the fare was ₹340."
4. Docker — what it actually is
Container = an isolated, lightweight mini-environment (own filesystem, own installed software) that boots in seconds — unlike a full VM which boots an entire OS.
Image = the blueprint/recipe. Container = the running instance built from that blueprint.
Docker Compose = a config file (docker-compose.yml) that defines multiple containers, puts them on a shared private network, and starts them together with one command (docker compose up).
5. Docker networking — the single most important gotcha
Inside a container, localhost means "this container itself" — NOT your laptop, NOT other containers.
Docker Compose gives each service a hostname equal to its service name (db, redis). Containers reach each other using these names, not localhost, not IP addresses.
This is why .env has POSTGRES_HOST=db and REDIS_HOST=redis.
6. Named volumes — data persistence
Containers are ephemeral (used for only a short period of time) by default — docker compose down deletes the container, and anything stored only in its filesystem is gone.
A named volume (e.g. postgres_data) is storage Docker manages outside any container's lifecycle. Declaring postgres_data:/var/lib/postgresql/data redirects Postgres's writes into that external volume.
Result: docker compose down → container deleted, volume survives. docker compose up again → new container, same volume reattached, all data intact.
Danger flag: docker compose down -v deletes volumes too — this destroys your data permanently. Never run -v unless you explicitly want a wipe.
7. Healthchecks + depends_on
Docker starting all containers simultaneously can cause your app to try connecting to Postgres before Postgres has actually finished initializing → connection errors on startup.
A healthcheck (e.g. pg_isready for Postgres, redis-cli ping for Redis) tells Docker "this service is truly ready," not just "the process started."
depends_on: condition: service_healthy makes the app container wait until db and redis both pass their healthchecks before starting.
8. Docker layer caching (Dockerfile optimization)
COPY requirements.txt . then RUN pip install... is done before COPY ./app ./app on purpose.
Docker caches each build step (layer). If only your code changes (not requirements), Docker reuses the cached dependency-install layer instead of reinstalling everything from scratch — turns a multi-minute rebuild into seconds.
9. --host 0.0.0.0 in uvicorn
Default host (127.0.0.1) only accepts connections from inside that exact container.
0.0.0.0 means "listen on all network interfaces" — required so requests from Docker's internal network or your browser (via port mapping) can actually reach uvicorn.
10. Diagnostic pattern for a broken service (general-purpose, not Docker-specific)

When something is unreachable, always check in this order:

docker compose ps — is the thing even alive? (status check — look for Up/healthy vs Exited)
docker compose logs <service_name> — if it's dead, why? (root cause from actual error output)
Only after confirming the service is alive do you move to checking config (hostnames, ports, env vars).
Principle: never debug "why can't I reach it" before confirming "is it even alive" — otherwise you waste time chasing the wrong layer.
One-Line Tradeoffs (memorize these verbatim style)
Redis vs Postgres for location: gain speed/scale, lose durability/queryability.
WebSockets vs polling (preview for Phase 2): gain real-time low-latency push, lose the simplicity of stateless request/response.
Named volumes: gain persistence across container teardown, at the cost of remembering to manage them explicitly (and not nuking them with -v).
What to Say If Asked "Walk Me Through Your Project's Infra" in an Interview

"I run a three-container setup via Docker Compose — a FastAPI app, PostgreSQL with the PostGIS extension for spatial/durable data, and Redis for high-frequency ephemeral data like live driver locations. Containers communicate over Docker's internal DNS using service names rather than localhost. Postgres data persists in a named volume so it survives container recreation, and I use healthchecks with depends_on to guarantee the app doesn't start before its dependencies are actually ready — not just running, but ready to accept connections."