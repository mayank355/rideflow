# RideFlow

A real-time ride-matching backend modeled on Uber's core architecture — built to demonstrate distributed systems fundamentals: hot/cold data separation, geospatial indexing, real-time push, and state machine design.

## Stack

- **FastAPI** — async Python web framework
- **PostgreSQL + PostGIS** — durable relational data (drivers, riders, trips)
- **Redis** — ephemeral geospatial data (live driver locations via `GEOADD`/`GEOSEARCH`)
- **WebSockets** — real-time push (match notifications, status updates, live location)
- **Docker + Docker Compose** — containerized, multi-service local environment

## Architecture

Two databases, deliberately split by access pattern:

| | Postgres | Redis |
|---|---|---|
| **Stores** | Driver/rider identity, trips, status, fare | Live driver GPS location |
| **Update frequency** | Occasional (registration, status changes) | Every 2-5 seconds |
| **Durability** | Required — survives restarts | Not required — self-healing, next ping overwrites |
| **Why** | ACID guarantees, relational integrity (foreign keys) | Fast writes, no write-amplification cost |

Rationale: if losing the data for 5 seconds is fine, it's in Redis. If losing it is never acceptable, it's in Postgres.

### Request flow: rider requests a ride

1. Rider hits `POST /rides/request` with pickup coordinates
2. Matching engine runs `GEOSEARCH` on Redis — finds nearby drivers, sorted by distance, in a single indexed query (not a linear distance-scan in application code)
3. Candidates are cross-checked against Postgres for `is_available = true`
4. Distance to the closest available driver is calculated (Haversine formula) → fare and ETA computed
5. A `Trip` row is committed to Postgres — this is the exact moment the match becomes durable, before any response leaves the server
6. Both rider and driver are notified live over WebSocket, using purpose-built payloads (driver gets pickup location; rider gets fare/ETA)

### Trip lifecycle

Trip status is an explicit state machine, not a free-form field:

```
REQUESTED → ONGOING → COMPLETED
REQUESTED → CANCELLED
ONGOING   → CANCELLED
```

`COMPLETED` and `CANCELLED` are terminal. Every transition is validated before being applied. Driver availability is flipped automatically as a side effect of each transition (busy during `ONGOING`, free again after `COMPLETED`/`CANCELLED`) — both changes commit in the same database transaction.

### Live tracking

While a trip is `ONGOING`, every driver location ping also pushes the new coordinates to the rider over WebSocket — the same mechanism that draws a moving car icon on a map in production ride-hailing apps. Reuses the existing Redis write path and WebSocket layer; no new infrastructure required.

## Known limitations (stated honestly, not hidden)

- **Haversine, not real routing distance** — straight-line distance is an approximation. Production systems use a routing engine (e.g. OSRM) with an actual road-network graph to account for one-ways, rivers, and live traffic.
- **Naive matching** — closest available driver wins. Production systems solve a batched, fleet-wide assignment optimization problem (e.g. Uber's H3 hexagonal indexing) rather than greedy nearest-match.
- **Simplified surge pricing** — a fixed time-of-day multiplier, not a live supply/demand computation per geographic zone.
- **No payment integration** — trip completion and payment settlement are collapsed into one state. Production systems insert an intermediate `PAYMENT_PENDING` state, since payment is an asynchronous external call.
- **Single-instance WebSocket registry** — the connection manager lives in one process's memory. Horizontally scaling to multiple app instances would require a pub/sub layer (e.g. Redis Pub/Sub) so any instance can deliver a push to a connection held by another.
- **No location push throttling** — every GPS ping during an active trip triggers a push. At scale, this would need distance- or time-based throttling.

## Running locally

```bash
docker compose up --build
```

Then visit `http://localhost:8000/docs` for interactive API documentation.

## API overview

| Endpoint | Purpose |
|---|---|
| `POST /drivers/register` | Register a new driver |
| `POST /drivers/{id}/location` | Report live location (Redis) |
| `POST /drivers/{id}/go-online` / `/go-offline` | Toggle availability |
| `POST /riders/register` | Register a new rider |
| `POST /rides/request` | Request a ride — triggers matching, fare/ETA, Trip creation |
| `PATCH /trips/{id}/status` | Transition trip status (state-machine validated) |
| `GET /trips/{id}` | Look up a single trip |
| `GET /trips/history/{rider_id}` | A rider's past trips |
| `WS /ws/driver/{id}` | Live push channel for a driver |
| `WS /ws/rider/{id}` | Live push channel for a rider |

## Project structure

```
app/
├── main.py                 # App entrypoint, router registration
├── database.py              # SQLAlchemy engine/session
├── models/                  # SQLAlchemy models (Driver, Rider, Trip)
├── schemas/                  # Pydantic request/response schemas
├── core/
│   ├── geo_utils.py            # Redis GEOADD/GEOSEARCH, Haversine distance
│   ├── matching.py              # Nearest-available-driver logic
│   ├── fare_calculator.py       # Fare formula + surge
│   ├── eta.py                    # ETA estimate
│   └── trip_state_machine.py     # Valid status transition rules
├── routers/                 # FastAPI route handlers
└── websocket/
    ├── manager.py               # In-memory connection registry
    ├── events.py                 # WebSocket event payload builders
    └── routes.py                  # WS endpoint definitions
```
