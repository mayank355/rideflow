Volumes persist data outside containers, -v destroys them
When something's unreachable: check if it's alive first, then check why it died, before touching config

In report_location(), the line

python
driver = db.query(Driver).filter(Driver.id == driver_id).first()
if not driver:
    raise HTTPException(status_code=404, detail="Driver not found")

runs before update_driver_location() is ever called. So the Postgres lookup returns None (no matching row), the if not driver check catches it, and the function exits immediately via the raised exception — Redis is never touched at all. No GEOADD call happens, nothing gets written anywhere.

Why this ordering matters, as a general principle: you're guarding a fast, cheap-to-corrupt store (Redis, no validation of its own) behind a check against your source of truth (Postgres). If you'd called update_driver_location() before checking Postgres, you'd end up with a Redis entry for a "driver" that doesn't actually exist in your system — a ghost location with no matching identity anywhere. That's the kind of subtle bug that doesn't crash anything immediately, but silently corrupts your data over time (e.g., a future GEOSEARCH could return a nonexistent driver as a match).

Interview line: "I validate identity against the source of truth before writing to the fast store — this prevents orphaned data in Redis that has no corresponding record in Postgres."

## ## Phase 4 — ETA & Fare Calculation
- Haversine-based distance calculation
- Dynamic fare: base + per-km + time-of-day surge
- ETA estimation, both persisted and pushed live via WebSocket

## Phase 5 — Trip Lifecycle
- Full state machine: requested → ongoing → completed/cancelled
- Driver availability auto-managed by trip status
- Trip history and lookup endpoints
- Go-online/go-offline endpoints (removed manual DB workarounds)

## Phase 6 — Live Trip Tracking
- Real-time driver location streaming to rider during active trips
- New WebSocket event: driver_location_update

## Alembic is NOT about live/real-time updates. It's about keeping the structure of your database consistent across different environments — your laptop, your teammate's laptop, your production server. It doesn't run automatically when someone uses the app; it only runs when a developer/deploy pipeline explicitly executes alembic upgrade head.

Concrete example to separate the two ideas:

Say you add a phone_number column to the drivers table:

You run alembic revision --autogenerate on your machine → generates a migration file
You commit that file to Git and push it
Your teammate pulls the code, runs alembic upgrade head on their machine → now their local database also has the phone_number column
When you deploy to production, the deploy pipeline runs alembic upgrade head on the production DB too → now production also has the column

So yes, the schema change eventually reaches everyone — but only because each person/environment explicitly runs the migration command. It's not automatic, and it's definitely not happening live while users are using the app. It's a deploy-time/dev-time operation.

What you were actually describing — data changing live across devices while people use the app — that's a completely different concept, and it's what your WebSocket layer (Phase 3) handles. Example: a driver's live location updates in Redis, and that update gets pushed instantly to the rider's phone via a WebSocket connection — that's real-time cross-device sync. Alembic has nothing to do with this.

Simple way to remember the difference:

	Alembic	WebSockets
What changes	Database structure (columns, tables)	Live data (driver location, ride status)
When it runs	Manually, by a developer, during deploy	Continuously, while the app is running
Who sees the effect	Anyone with a fresh copy of the DB, after they run the migration	Connected users, instantly, in real time
Analogy	Renovating a house's blueprint	People walking around inside the house right now

So to directly answer your question: no, Alembic doesn't push live updates to other devices. It just makes sure everyone's database structure matches, whenever they choose to run it.