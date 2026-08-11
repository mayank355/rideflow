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