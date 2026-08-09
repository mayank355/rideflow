1. What This Project Actually Tests

Uber's core hard problem isn't CRUD — it's: thousands of drivers moving every few seconds, and you need to answer "who is closest to this rider" in under 100ms, consistently, while also writing every trip to a durable ledger.

That's three separate problems bolted together:

High-frequency, ephemeral, spatial writes (driver location — updates every 2-5 sec, old data is garbage)
Low-latency spatial reads (find nearest driver — must be fast, doesn't need ACID)
Low-frequency, durable, relational writes (trip history — needs ACID, needs joins, needs to never disappear)

This is why the stack has two databases (Postgres + Redis) instead of one. If you understand why you need both, you understand the entire project. This is a "storage system design" answer in disguise — this is exactly what DE Shaw/Citadel infra rounds probe.

2. Architecture Diagram (text)
                              ┌─────────────────┐
                              │   Rider (App)    │
                              └────────┬─────────┘
                                       │ HTTP: POST /rides/request
                                       │ WS: /ws/rider/{id}
                                       ▼
                        ┌──────────────────────────────┐
                        │         FastAPI App            │
                        │  ┌──────────┐  ┌────────────┐ │
                        │  │  Routers  │  │  WebSocket  │ │
                        │  │  (REST)   │  │  Manager    │ │
                        │  └────┬─────┘  └──────┬──────┘ │
                        │       │               │        │
                        │  ┌────▼───────────────▼─────┐  │
                        │  │   Matching Engine (Core)  │  │
                        │  └────┬──────────────┬───────┘  │
                        └───────┼──────────────┼──────────┘
                                │              │
                    ┌───────────▼──┐      ┌────▼────────────┐
                    │    Redis      │      │   PostgreSQL     │
                    │  (Hot Path)   │      │   + PostGIS      │
                    │               │      │   (Cold Path)    │
                    │ GEO driver    │      │ - drivers table  │
                    │ locations     │      │ - riders table   │
                    │ (live, TTL)   │      │ - trips table    │
                    │               │      │ - trip_status    │
                    │ driver status │      │   history        │
                    │ (online/busy) │      │                  │
                    └───────────────┘      └──────────────────┘
                                ▲
                                │ WS: driver pushes location every 2-5s
                        ┌───────┴─────────┐
                        │  Driver (App)    │
                        └──────────────────┘

Read this diagram as: Redis is the nervous system (fast, reflexive, forgets things). Postgres is the long-term memory (slow, durable, remembers everything forever). Every real-time system that scales has this split — it's called hot path / cold path separation, and you should use that exact phrase in interviews.

3. End-to-End Request Flow (what actually happens)
Driver app connects via WebSocket → sends lat/lng every few seconds.
Backend writes driver's location into Redis using a geospatial command (GEOADD) — NOT Postgres. Old location is simply overwritten. No history kept here.
Rider hits POST /rides/request with pickup lat/lng.
Backend queries Redis (GEOSEARCH) → "give me all drivers within 3km of this point, sorted by distance."
Backend filters those by status (online, not on_trip) — status also lives in Redis for speed.
Matching engine picks one (nearest-first for now, weighted logic later), assigns the trip.
A row is created in Postgres trips table — this is the durable event. This is the only place a trip officially "exists."
WebSocket pushes driver_assigned to rider, ride_requested to driver.
As the trip progresses, status changes push through WebSocket; final state (completed, fare, distance, duration) gets written back to Postgres.

The rule to internalize: If losing the data for 5 seconds is fine → Redis. If losing the data ever is not fine → Postgres. That one sentence is your answer to "why two databases" in any interview.

4. File Structure (what we'll build, in order)
rideflow/
├── docker-compose.yml          # Spins up: FastAPI app, Postgres+PostGIS, Redis
├── Dockerfile                  # Container build for the FastAPI app
├── requirements.txt
├── .env                        # DB_URL, REDIS_URL, secrets
│
├── app/
│   ├── main.py                 # FastAPI app instance, router registration, startup events
│   ├── config.py                # Settings (pydantic BaseSettings) — env var loading
│   ├── database.py              # SQLAlchemy engine + session (Postgres)
│   ├── redis_client.py          # Redis connection pool + geo helper functions
│   │
│   ├── models/
│   │   ├── driver.py             # SQLAlchemy model: Driver (id, name, vehicle, created_at)
│   │   ├── rider.py               # SQLAlchemy model: Rider
│   │   └── trip.py                 # SQLAlchemy model: Trip (rider_id, driver_id, status, fare, distance, timestamps)
│   │
│   ├── schemas/
│   │   ├── driver.py              # Pydantic: DriverCreate, DriverOut, LocationUpdate
│   │   ├── rider.py
│   │   └── trip.py                 # RideRequest, TripOut, TripStatusUpdate
│   │
│   ├── routers/
│   │   ├── drivers.py              # POST /drivers/register, POST /drivers/{id}/location
│   │   ├── riders.py                 # POST /riders/register
│   │   └── trips.py                    # POST /rides/request, GET /trips/{id}, GET /trips/history/{rider_id}
│   │
│   ├── core/
│   │   ├── matching.py               # THE matching algorithm — nearest driver logic lives here
│   │   ├── geo_utils.py                # Haversine/distance math, geohash helpers if needed
│   │   ├── fare_calculator.py          # Distance + time + surge → fare
│   │   └── eta.py                      # ETA estimation logic
│   │
│   └── websocket/
│       ├── manager.py                 # ConnectionManager — tracks active WS connections per user
│       └── events.py                    # Event payload schemas (ride_requested, driver_assigned, trip_completed)
│
├── alembic/                      # DB migrations (you'll need this — schema will evolve)
│   └── versions/
│
└── tests/
    └── test_matching.py           # Unit tests for matching logic (interviewers WILL ask if you have tests)

Nothing here is decorative. If a file exists, it's because a specific responsibility needed to be isolated — that separation itself is a talking point (single responsibility, testability).

5. Build Order (phases)

We are not building this top-to-bottom by file. We build by capability, testing each before moving on:

Phase	What you build	Proves you understand
0	Docker Compose: Postgres+PostGIS, Redis, FastAPI wired together	Multi-service orchestration
1	Driver registration (Postgres) + live location write (Redis GEOADD)	Hot/cold path split
2	Rider request → nearest driver query (Redis GEOSEARCH) + naive matching	Geospatial querying, matching logic
3	WebSocket layer — push live status to rider & driver	Real-time bidirectional communication
4	ETA + fare calculation	Applying domain logic on top of geo data
5	Trip persistence + full status lifecycle in Postgres	Durable state machine design
6	Load thinking: what breaks first, how you'd fix it at 10x/100x	System design maturity — this is what gets you hired, not the code
6. The Big Architectural Decisions (interview-ready, right now)
Decision 1: Redis for live location, not Postgres
What it is: Redis is an in-memory key-value store. It has a geospatial data type (backed by a sorted set) supporting GEOADD (store a point) and GEOSEARCH (find points within a radius, sorted by distance).
Why here: Driver location changes every few seconds. If you write that to Postgres, you're doing thousands of UPDATE statements per second on a disk-backed relational table with indexes to maintain. That's an unnecessary write amplification problem.
Problem it solves: Decouples "data that must survive a crash" from "data that's stale in 5 seconds anyway."
At 10x/100x scale: Single Redis instance becomes a bottleneck and single point of failure. You'd shard driver locations across a Redis Cluster using consistent hashing (so drivers in a geographic region hash to the same node, minimizing cross-node queries). At Uber's actual scale, this evolves into custom geo-sharded services (they built "Ringpop"/geo-partitioned services for exactly this).
Interview answer: "I chose Redis because driver location is high-write, low-durability-requirement data — geospatial lookups need to happen in single-digit milliseconds, and losing a few seconds of location history is acceptable. Postgres would work but its write path (WAL, indexes, MVCC) is overhead I don't need for data that's irrelevant in 5 seconds."
Tradeoff in one sentence: You gain write/read speed and horizontal scalability, and you lose durability and queryability (no SQL joins, no historical location analysis without a separate pipeline).
Decision 2: PostGIS for trip/durable spatial data
What it is: A Postgres extension adding spatial data types and functions (distance, containment, indexing via GiST) directly into SQL.
Why here: Trip records need spatial data (pickup/dropoff points) and relational integrity (foreign keys to driver/rider, joins for reporting, ACID guarantees for billing).
Problem it solves: You don't want two disconnected systems for "spatial" — PostGIS lets you do ST_Distance in the same query as a JOIN on trips.rider_id.
At scale: PostGIS on a single Postgres instance handles surprising scale (Uber initially used Postgres/PostGIS-like systems before moving to custom geo-indexes). At 100x, you'd look at read replicas for analytics queries and eventually a dedicated geospatial index service, but PostGIS is rarely the first thing you rip out.
Interview answer: "For durable trip data I need relational guarantees — a trip must reference exactly one driver and rider, fares must be accurate, and I need to run analytical queries later. PostGIS gives me spatial capability without sacrificing SQL's relational integrity."
Tradeoff: You gain consistency and expressive querying; you lose the raw write throughput Redis gives you for high-frequency updates.
Decision 3: WebSockets, not polling or Server-Sent Events
What it is: A persistent, full-duplex TCP connection between client and server — either side can push a message anytime, no new HTTP request needed per message.
Why here: Both driver and rider need to receive pushes (status changes, location of the matched driver) without asking "anything new?" every second.
Problem it solves: Polling means every client hammers your server every N seconds regardless of whether anything changed — wasteful and adds latency (average delay = poll interval / 2). SSE is push-only server→client; we need driver→server too (location updates), so full-duplex wins.
At scale: A single FastAPI process can hold thousands of WS connections, but it's stateful — a connection lives on one server process. At 10x/100x you need a way to route "push this message to user X" across many server instances → this is where you'd introduce a pub/sub layer (Redis Pub/Sub or Kafka): any server instance publishes an event, the instance actually holding that user's WS connection subscribes and forwards it.
Interview answer: "WebSockets because I need bidirectional low-latency communication — drivers push location, riders receive status pushes. Polling would add both latency and unnecessary load proportional to poll frequency, not to actual state changes."
Tradeoff: You gain real-time low-latency delivery; you lose simplicity — WS connections are stateful and don't horizontally scale for free like stateless REST does.
Decision 4: Matching algorithm — start naive, name the sophisticated version
What it is (v1, what we build): Radius search via Redis GEOSEARCH, sorted by distance, pick nearest available driver.
Why here: Correct, simple, and demonstrates the core mechanism. Not what Uber actually runs in production, and you should say that unprompted in an interview — it shows you know the difference between "a working solution" and "the production solution."
What Uber actually does at scale: Doesn't just pick nearest — optimizes for global marketplace efficiency (a driver 2 minutes away might be better held for a longer trip elsewhere). Uses H3 (hexagonal hierarchical geospatial indexing) instead of simple radius/geohash, batches matching in short windows instead of matching instantly one-by-one, and treats it as a bipartite matching / assignment optimization problem, not a nearest-neighbor lookup.
Interview answer: "My matching engine does a geospatial radius query and picks the nearest available driver — this is correct but greedy. At scale, this becomes a global assignment optimization problem: you batch requests over a short window and solve a bipartite matching problem to maximize overall trip efficiency, not just minimize individual pickup distance. Uber uses hexagonal spatial indexing (H3) instead of simple radius search because it's more efficient for dense urban areas with irregular road networks."
Tradeoff: Naive nearest-match is simple and low-latency per request; global optimization improves fleet efficiency but adds latency (you wait to batch) and complexity.
Decision 5: Location updates as a stream — where Kafka fits (not implemented, but you must be able to say why)
What it is: Kafka is a distributed append-only log — producers write events, consumers read them independently, at their own pace, and the log persists them for a retention window.
Why we're NOT using it here: At our scale, direct Redis writes are enough. Kafka adds operational complexity (brokers, partitions, consumer groups) that buys you nothing at hundreds of req/sec.
When a company like Uber would use it: Once you have multiple downstream consumers of the same location stream — matching engine, fraud detection, surge pricing calculator, analytics pipeline, ETA model — you don't want each one hitting Redis directly. You publish location updates to Kafka once, and every consumer reads independently at its own pace. It also gives you replay (reprocess yesterday's data) which Redis (ephemeral) cannot.
Interview answer: "I didn't use Kafka because I have one consumer of location data — the matching engine. Kafka earns its complexity when you have multiple independent consumers needing the same event stream, or when you need durability/replay of a high-throughput event log. Introducing it here would be premature complexity."
Tradeoff in one sentence: Kafka buys you decoupled multi-consumer durability and replay at the cost of operational overhead you don't need until you actually have multiple consumers.
Decision 6: Docker + Railway now, Kubernetes later
Why here: Docker Compose is enough for one FastAPI instance + one Postgres + one Redis. Railway handles deployment without you managing infra.
When Kubernetes enters: When you need to run multiple instances of the FastAPI app (horizontal scaling under load) with auto-restart, rolling deploys, and load balancing across them — Kubernetes automates that. At your current scale it's pure overhead.
Interview answer: "Single-instance deployment doesn't need an orchestrator. Kubernetes becomes necessary once you're running multiple replicas of a service and need automated scheduling, health checks, and rolling deployments — solving a problem I don't have yet."
Tradeoff: Simplicity now vs. horizontal scalability and self-healing later.

## phase 0
Phase 0: Project Skeleton + Docker Compose
Why we start here (before writing a single API route)

Right now you have three moving parts that need to talk to each other: your FastAPI app, a PostgreSQL database, and a Redis instance. In your Text Logger project, you probably ran Postgres locally or used a single hosted DB URL. Here, we need three separate services running and networked together, and we want that setup to work identically on your laptop and on Railway later. That's exactly the problem Docker solves.

Concept 1: What is Docker, really (plain English)

Think of your laptop as a shared apartment. If you install Postgres directly on your machine, and later a groupmate needs a different Postgres version for their project, you get conflicts — port clashes, version mismatches, "works on my machine" bugs.

A container is like giving each service its own fully furnished, isolated mini-apartment — its own filesystem, its own installed software, completely walled off from your actual laptop and from other containers. It boots up in seconds (unlike a full virtual machine, which boots a whole OS).

A Docker image is the blueprint/floor-plan for that apartment (e.g., "official Postgres 16 image" = a pre-built recipe for a Postgres apartment). A container is the actual apartment built from that blueprint, running live.

Concept 2: What is Docker Compose

Docker runs one container at a time by default. But we need three containers (FastAPI app, Postgres, Redis) that can find and talk to each other. Docker Compose is a config file (docker-compose.yml) where you describe: "spin up these three apartments, put them on the same private hallway (network) so they can knock on each other's doors, and here's which apartment number (port) maps to what."

Without Compose, you'd manually run three docker run commands with a dozen flags each, every single time. Compose = one command (docker compose up) does all three, wired correctly, every time.

Concept 3: Why PostGIS specifically, not plain Postgres

PostGIS is not a separate database — it's an extension you install into Postgres that adds spatial data types (like "a point on Earth") and spatial functions (like "give me the distance in meters between these two points, accounting for the Earth's curvature"). Plain Postgres has no idea what a latitude/longitude pair means geographically — PostGIS teaches it geography.

We use the postgis/postgis Docker image instead of plain postgres — same Postgres underneath, just pre-installed with the extension so you don't have to manually enable it.

Concept 4: Why environment variables / .env file

Your database needs a username, password, and connection URL. Redis needs a host and port. You never hardcode these into your Python files — if you do, and you ever push this to GitHub (which you will, for placements — companies check your GitHub), your DB password is now public forever.

Instead, we put these values in a .env file (which we tell Git to ignore via .gitignore), and our code reads them at runtime via environment variables. This is standard practice — expect this exact question in interviews: "how do you handle secrets/config?"

What we're building right now, file by file
.env — holds Postgres credentials, Redis URL, app secrets
docker-compose.yml — defines 3 services: app (FastAPI), db (Postgres+PostGIS), redis
Dockerfile — instructions for building the FastAPI app's own container image (install Python deps, copy code, run uvicorn)
requirements.txt — Python dependencies
app/main.py — minimal FastAPI app with a health-check route, just to prove all three containers can boot and talk

We are NOT writing any driver/rider/matching logic yet. The only goal of Phase 0 is: run one command, get three containers up, and confirm FastAPI can successfully connect to both Postgres and Redis. That's it. This is the "does the plumbing work" phase.

## about files and setup


.env — secrets and config (never committed to Git)
Examined Docker networking service resolution mechanics
Examined Docker networking service resolution mechanics

Notice something important: POSTGRES_HOST=db and REDIS_HOST=redis — not localhost. This is the single most common beginner mistake with Docker Compose, so understand it now:

When your FastAPI app runs inside a container, localhost means "this container itself" — not your laptop, not the other containers. Docker Compose creates an internal private network where each service is reachable by its service name (like a hostname). So when the app container wants to reach Postgres, it doesn't say "localhost:5432" — it says "db:5432", because db is literally the name we'll give the Postgres service in docker-compose.yml. Same for redis. Keep this in your head — it's the #1 thing that confuses people moving from "Postgres running locally" to "Postgres running in a container."

.gitignore — so .env and junk never reach GitHub
Creating .gitignore
Creating .gitignore
requirements.txt — dependencies, explained by why each exists
Creating requirements.txt
Creating requirements.txt

What each one is for, since some are new to you:

fastapi, pydantic — you know these from Text Logger.
uvicorn[standard] — the actual server that runs your FastAPI app. The [standard] extra installs support for WebSockets and better performance libraries under the hood — without it, WebSockets won't work properly.
sqlalchemy, psycopg2-binary — you know these too (ORM + Postgres driver).
geoalchemy2 — new. This is the bridge between SQLAlchemy and PostGIS. Plain SQLAlchemy doesn't know what a "geographic point" column type is — GeoAlchemy2 adds that, so you can define a location column in a Python model and have it map to PostGIS's spatial type correctly.
pydantic-settings — lets you load .env variables into a typed Python config class (cleaner than raw os.environ.get() everywhere).
redis — the Python client library to talk to Redis (send GEOADD, GEOSEARCH, etc.).
python-dotenv — loads .env file variables into the environment when running locally (outside Docker, Docker Compose handles this itself, but good to have for flexibility).
alembic — migration tool for Postgres schema changes. You said you used SQLAlchemy before — did you use Alembic for migrations, or did you just call Base.metadata.create_all()? This matters for how I explain Phase 1, so keep that in mind, I'll ask when we get there.
websockets — low-level WebSocket protocol library that FastAPI/Starlette relies on.
Dockerfile — blueprint for the FastAPI app's container
Synthesized Docker optimization, networking nuances, and development tooling considerations
Synthesized Docker optimization, networking nuances, and development tooling considerations

Line-by-line, the parts that aren't obvious:

FROM python:3.11-slim — every Docker image starts from a base image. slim is a stripped-down Debian with just enough to run Python — smaller size, faster builds, than the full image.
RUN apt-get install libpq-dev gcc — psycopg2 (the Postgres driver) needs to compile some C code against Postgres's client library during install. Without libpq-dev and a C compiler (gcc) present in the container, pip install psycopg2-binary would fail. (We're using psycopg2-binary which is precompiled, but keeping this is safer/more portable — you'll hit this exact issue in real deployments if you ever switch to plain psycopg2.)
Why COPY requirements.txt . happens before COPY ./app ./app, as two separate steps — this is a deliberate optimization called Docker layer caching. Docker builds images in layers, and caches each layer. If you change your Python code but not your requirements, Docker sees "the requirements.txt layer is unchanged" and skips reinstalling all your dependencies from scratch — it reuses the cached layer. If you'd copied everything at once, changing a single line of code would force a full dependency reinstall every time you rebuild. This ordering trick alone can turn a 2-minute rebuild into a 3-second rebuild. This is a real interview talking point for "how do you optimize Docker builds."
EXPOSE 8000 — documents which port the container listens on (doesn't actually publish it to your host machine — that happens in docker-compose.yml).
--host 0.0.0.0 — critical, common bug source. If you run uvicorn with the default host (127.0.0.1), it only accepts connections from inside that exact container. 0.0.0.0 means "listen on all network interfaces," which is required for the request coming from Docker's internal network (or from your browser via the port mapping) to actually reach uvicorn. Forgetting this is the #1 reason people's "it built fine but I can't access it" bug happens.
--reload — auto-restarts the server when code changes. Great for development, but we will remove this in production (Railway deployment) since it adds overhead and is a dev-only convenience.
docker-compose.yml — wiring all three services together
Synthesized Docker Compose architecture and service orchestration fundamentals
Synthesized Docker Compose architecture and service orchestration fundamentals

Now the concepts that matter here — go slow with this one, it's the core of Phase 0:

services: — each block (db, redis, app) is one container. The name you give it (db, redis) is also its hostname on the internal Docker network — this is exactly why .env said POSTGRES_HOST=db, not some IP address. Docker Compose runs a built-in DNS so containers can find each other by these names.

image: vs build: — for db and redis, we use image: because we're pulling a pre-made image from Docker Hub (someone already built "Postgres+PostGIS" and "Redis" images — no reason to build our own). For app, we use build: . because our FastAPI code needs a custom image — Docker will use the Dockerfile in the current directory to build it.

ports: "5432:5432" — format is "HOST_PORT:CONTAINER_PORT". Left side (5432) is the port on your actual Windows machine. Right side is the port inside the container. We're mapping them 1:1 here so you can optionally connect to Postgres from a GUI tool like TablePlus/pgAdmin on your laptop for debugging, outside of Docker's internal network.

volumes: postgres_data:/var/lib/postgresql/data — this is critical and easy to miss. Containers are ephemeral by default — if you stop and remove a container, everything written inside it disappears, including your database data. A volume is a persistent storage location managed by Docker, living outside the container's lifecycle. We're telling Postgres "store your actual data files in this volume," so even if you tear down and rebuild the db container, your data survives. Without this line, every docker compose down would wipe your entire database. This is not optional for a database container — ever.

volumes: ./app:/code/app under app service — different purpose. This is a bind mount — it maps your actual local folder (./app on your Windows machine) directly into the container's /code/app. Combined with uvicorn's --reload flag, this means: you edit a Python file in VS Code on Windows → the change is instantly visible inside the running container → uvicorn auto-restarts. Without this, you'd have to rebuild the entire image every time you changed one line of code, which is painfully slow for development. (We'll remove this bind mount for the production/Railway setup later — production wants the code baked into the image, not live-mounted.)

healthcheck: — Docker needs a way to know "is Postgres actually ready to accept queries yet," not just "has the container process started." pg_isready is Postgres's own built-in command for exactly this check. Same idea for Redis with redis-cli ping.

depends_on: db: condition: service_healthy — this is the payoff of the healthcheck. Without this, Docker Compose would start all three containers simultaneously, and there's a real chance your FastAPI app tries to connect to Postgres in the split-second before Postgres has actually finished initializing — causing a connection error on startup. depends_on with condition: service_healthy tells Docker: "don't even start the app container until db and redis have both passed their healthchecks." This is a genuinely common bug in real-world Docker setups — people get random "connection refused" errors on docker compose up because they skipped this.

app/main.py — minimal app just to prove the plumbing works
Orchestrated database and cache validation checks
Orchestrated database and cache validation checks

What this file does, briefly:

create_engine(DATABASE_URL) — SQLAlchemy's connection pool to Postgres. You've done this before.
redis.from_url(REDIS_URL) — same idea for Redis, creates a client connection.
/health route runs the simplest possible check against each: SELECT 1 for Postgres (a query with zero real logic, just proving the connection + query execution works), and .ping() for Redis (Redis's built-in "are you alive" command). This route is temporary — its only job is to prove Phase 0 succeeded. We'll delete it once real functionality exists.