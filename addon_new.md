## Next: Location Push Throttling
Quick concept (fast version)

Right now, every single POST /drivers/{id}/location call during an ongoing trip pushes to the rider — no matter how small the movement. We'll add a cheap guard: only push if the driver moved more than ~15 meters since the last push for that trip, using an in-memory dict tracking last-pushed coordinates per trip. This avoids flooding the rider with pushes for a car sitting still or barely moving.

Implementation
Edited a file, created a file
Edited a file, created a file

Now wire it into the driver location endpoint, and clear tracking on trip completion:

Edited 2 files
Edited 2 files

Now clear tracking when a trip ends, in trips.py's status update endpoint:

Edited 2 files, ran a command
Edited 2 files, ran a command

Package it:

Ran a command, read a file
Ran a command, read a file
Summary — Location Push Throttling

Files: app/core/location_throttle.py (new), app/routers/drivers.py (modified), app/routers/trips.py (modified)

What it does: tracks the last-pushed position per trip in memory; only pushes a new driver_location_update if the driver moved ≥15 meters since the last push. Every ping still writes to Redis regardless (matching/ETA need fresh data) — only the rider-facing push is throttled. Tracking is cleared when a trip ends, to avoid unbounded memory growth.

Interview line: "Every location ping still updates Redis, but I only push to the rider's WebSocket if they moved a meaningful distance since the last push — this cuts unnecessary traffic from GPS jitter or a stationary car without losing responsiveness. I clean up tracking state when a trip ends so this doesn't leak memory over the app's lifetime."

No rebuild instructions needed right now — copy app/core/location_throttle.py, app/routers/drivers.py, app/routers/trips.py into your project, rebuild, test same as Phase 6 but move coordinates less than 15m between two calls and confirm the second push is skipped.

Moving immediately to next: Payment-Pending state.

Concept

Insert PAYMENT_PENDING between ONGOING and COMPLETED. Driver stays unavailable until payment settles (matches real-world behavior discussed in Phase 5).

Ran a command, edited a file
Ran a command, edited a file

Update the state machine:

Architected payment state transitions and driver availability logic
Architected payment state transitions and driver availability logic

Now the availability logic already works correctly — it only flips is_available back to true on COMPLETED/CANCELLED, so a trip sitting in PAYMENT_PENDING correctly keeps the driver unavailable, with zero extra code needed. Let's add the Alembic migration for this enum change:

Creating migration for PAYMENT_PENDING enum value
Creating migration for PAYMENT_PENDING enum value

Now update the update_trip_status endpoint's docstring/logic reference for clarity (logic itself is already correct):

Ran a command
Ran a command

This is already correct — PAYMENT_PENDING isn't in either branch, so is_available simply stays false through that state, exactly as intended. Just update the docstring to reflect the new state explicitly:

Updating docstring to mention PAYMENT_PENDING
Updating docstring to mention PAYMENT_PENDING

Package it:

Ran a command, read a file
Ran a command, read a file
Summary — Payment-Pending State

Files: app/models/trip.py, app/core/trip_state_machine.py, app/routers/trips.py, alembic/versions/0002_add_payment_pending.py (new)

What changed: new PAYMENT_PENDING status between ONGOING and COMPLETED. Flow is now REQUESTED → ONGOING → PAYMENT_PENDING → COMPLETED (or CANCELLED from REQUESTED/ONGOING). Driver stays unavailable through PAYMENT_PENDING automatically — no new code needed for that, since availability only resets on COMPLETED/CANCELLED.

Interview line: "I added a payment-pending state between the ride ending and the trip being marked complete — mirroring real systems, where payment is an asynchronous external call, and a driver isn't freed until it settles, not the instant the ride physically ends."

Setup: copy the 4 files, rebuild, then run docker exec -it rideflow_app alembic upgrade head to apply the new enum value (this one applies automatically via entrypoint on next restart too).

Moving immediately to next: Trip route history (storing the path for replay).

Creating TripLocationLog model for route history
Creating TripLocationLog model for route history

Now wire logging into the location endpoint, and add a route-history GET endpoint:

Edited 2 files
Edited 2 files

Add the route-history endpoint in trips.py:

Edited 2 files
Edited 2 files

Register the new model in main.py and Alembic's env.py, plus write the migration:

Edited 2 files, created a file
Edited 2 files, created a file

Package everything:

Ran a command, read a file
Ran a command, read a file
Summary — Trip Route History

Files: app/models/trip_location_log.py (new), app/routers/drivers.py, app/routers/trips.py, app/main.py, alembic/env.py, alembic/versions/0003_trip_location_logs.py (new)

What it does: every location ping during an active trip now writes a durable row to a new trip_location_logs table (never throttled — full history always kept), separate from Redis's ephemeral current-position and separate from the throttled WebSocket push. New GET /trips/{trip_id}/route returns the full chronological path.

Key interview point: this is an INSERT-only table (never UPDATE), so it doesn't reintroduce the write-amplification problem from Phase 0 — MVCC dead-tuple bloat comes from repeated updates to the same row, not from appending new rows. Worth stating explicitly if asked "doesn't writing every 2-3 seconds cause the same problem as before?"

Interview line: "This looks like it might reintroduce the write-amplification issue from early on, but it doesn't — that problem came from repeatedly updating the same row. This is append-only inserts, which don't create the same dead-tuple/vacuum pressure."