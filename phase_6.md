## Phase 6: Continuous Trip Tracking — Live GPS During an Active Ride
Real-world analogy first

Think about the difference between checking a flight's status once when you book it, versus watching the little airplane icon crawl across the map in a live flight-tracking app while the flight is actually in the air. Right now, RideFlow only knows a driver's location at two moments: whenever they happen to ping it (which we've been doing manually in tests), and that's it — there's no continuous "here's where the car actually is right now, updating every few seconds while the ride is in progress."

Phase 6 is building that live-tracking map view — the same mechanism Uber uses to show a rider a moving car icon creeping toward their pickup point, and later, moving toward their destination.

Why this phase doesn't need much new machinery

Here's the good news, and it's worth appreciating: you already have every piece required. POST /drivers/{driver_id}/location already writes to Redis every time it's called (Phase 1). The WebSocket push mechanism already exists (Phase 3). This phase's real "new" idea is narrow: when a driver reports their location AND they currently have an active (ongoing) trip, also push that location to the rider over WebSocket — reusing everything, adding one conditional check and one new event type.

The interesting engineering question this phase actually raises

If a driver's app pings location every 2-3 seconds during an active trip, and we push every single one of those pings straight to the rider, we're now pushing potentially 20-30 messages per minute per active trip. At low usage, that's nothing. At scale — thousands of concurrent trips — that's a meaningful amount of WebSocket traffic. This is a legitimate moment to discuss throttling/rate-limiting push frequency, which is exactly the kind of practical scaling conversation interviewers like.

What we're exactly building in Phase 6
Extend POST /drivers/{driver_id}/location — after writing to Redis (unchanged), check if this driver has a currently ongoing trip. If so, push a driver_location_update event to that trip's rider.
A helper to find a driver's active trip — a simple Postgres query: "does this driver have any trip with status = ongoing right now?"
New WebSocket event: driver_location_update — just lat/lng and trip_id, nothing else needed.
A brief, honest discussion (not full implementation) of throttling — we'll note the real concern and the standard fix (e.g., only push if the driver moved more than N meters since the last push, or push at most once every X seconds) without over-engineering it into this phase.

We're not building route replay/trip playback history (storing every ping for later viewing) — that would require a new table and is a reasonable Phase 7+ extension, not core to "live tracking works."

## On throttling — the practical concern, stated without over-building it

Right now, every single location ping (potentially every 2-3 seconds) during an active trip triggers an immediate WebSocket push. At one trip, that's nothing. At thousands of concurrent active trips, that's a meaningful steady stream of WebSocket writes across your server. The standard fixes, worth naming in an interview without implementing all of them here:

Distance-based throttling: only push if the driver has moved more than some threshold (e.g., 20 meters) since the last push — a car sitting at a red light shouldn't generate pushes.
Time-based throttling: cap pushes to at most once every N seconds regardless of how often location updates arrive, decoupling "how often the driver's GPS reports" from "how often the rider's screen needs to redraw."

## RideFlow — Phase 6 Summary (Live Trip Tracking)
What Phase 6 Actually Was

Extended the existing location-reporting mechanism so that, during an active (ongoing) trip, every driver location ping also gets pushed live to the rider over WebSocket — the actual "moving car icon on a map" mechanism used by every real ride-hailing and delivery app. This phase added almost no new machinery; it reused Redis writes (Phase 1), WebSocket push (Phase 3), and the Trip table (Phase 2) to compose a new behavior.

The Real-World Analogy

Checking a flight's status once at booking versus watching a live flight-tracker app show the plane icon crawling across a map in real time. RideFlow previously only knew a driver's location at whatever moment it happened to be pinged. Phase 6 makes that continuous and visible to the rider specifically while a ride is in progress — not before, not after.

Core Concepts — Interview Ready
1. Why this phase needed almost no new infrastructure — and why that's worth pointing out unprompted
POST /drivers/{driver_id}/location already wrote to Redis on every call since Phase 1. The WebSocket push mechanism already existed since Phase 3. The Trip table already linked rider_id and driver_id since Phase 2.
The only genuinely new piece was a single conditional: if this driver has an active trip right now, also push their location to that trip's rider.
Interview line: "This phase composed three pieces I'd already built rather than introducing new infrastructure — that's a sign the earlier architecture was factored correctly. Live tracking is really just 'reuse the existing location write path, add one lookup, add one push,' not a separate subsystem."
2. No new pairing table needed — Trip already is the pairing
To find "which rider is this driver currently serving," the obvious naive instinct might be a new rider↔driver relationship table. That's unnecessary: Trip already stores rider_id, driver_id, and status on the same row.
find_active_trip_for_driver is a single query: WHERE driver_id = ? AND status = 'ongoing'. If a row comes back, that trip's rider_id is exactly who should receive the location push.
Interview line: "I didn't need a new table to track who's paired with whom — the Trip table, combined with its status field, already answers that question. Reusing existing schema instead of introducing redundant relationships is a design habit worth calling out."
3. The query determines whether ANY push happens at all
Before a trip reaches ongoing, find_active_trip_for_driver returns nothing, and location pings behave exactly as they did in Phase 1 — write to Redis, nothing more. Only once the state machine (Phase 5) transitions a trip into ongoing does the exact same location endpoint start doing something new.
This is a clean illustration of how the trip lifecycle from Phase 5 and the live tracking from Phase 6 compose together correctly: one phase's state directly gates another phase's behavior, without either needing to know the other's internals beyond a status check.
4. The honest scaling concern: push frequency, named without over-engineering it
If a driver's app pings location every 2-3 seconds during an active trip, and every ping triggers an immediate push, one active trip generates roughly 20-30 WebSocket messages per minute. Trivial at low usage; a real cost at thousands of concurrent active trips.
The two standard fixes, named but deliberately not implemented here:
Distance-based throttling — only push if the driver moved more than some threshold (e.g. 20 meters) since the last push, so a car stopped at a red light doesn't generate redundant pushes.
Time-based throttling — cap pushes to at most once every N seconds regardless of raw ping frequency, decoupling how often GPS reports from how often the rider's screen actually needs to redraw.
Interview line: "Right now every location ping during an active trip triggers a push — fine at low scale, but at high concurrent trip counts you'd want throttling, either distance-based (only push after meaningful movement) or time-based (cap push frequency independent of raw GPS frequency). I didn't implement that here because the goal of this phase was proving the mechanism works end-to-end; throttling is a known, understood next optimization, not a blind spot."
5. Asymmetric by design, same principle as Phase 4/5
driver_location_update is pushed only to the rider, never the driver — a driver doesn't need to be told their own current position back.
This is the same "not every event needs identical treatment for every recipient" judgment call made explicitly in Phase 4 (ride_assigned vs driver_found) and Phase 5 (trip_status_updated being symmetric). Recognizing which pattern applies to a new event, rather than defaulting to one style, is the actual skill being demonstrated across all three phases.
6. Minimal, purpose-built event payload
driver_location_update carries only trip_id, latitude, longitude — nothing else. No driver id, no timestamp, no extra metadata.
Why minimal is correct here, not lazy: the rider's client only needs enough to move a marker on a map for a specific trip it's already tracking. Anything more would be unused weight on a message sent potentially dozens of times per minute per active trip — payload size matters more here than on a one-off event like driver_found.
One-Line Tradeoffs (memorize these)
Reusing the Trip table for pairing vs a dedicated relationship table: gain zero schema duplication and one less table to keep in sync, lose nothing — a clearly correct reuse, not really a tradeoff.
Push-every-ping now vs throttled pushes later: gain simplicity and a fully working proof of mechanism today, lose bandwidth/message-volume efficiency at high concurrent-trip scale — explicitly deferred with the correct fix already identified.
Minimal event payload vs a richer one: gain lower per-message overhead on a high-frequency event, lose flexibility if a future feature needs more context in the same message — an acceptable bet given how this specific event is used.
What to Say If Asked "How Does Live Tracking Work" in an Interview

"During an active trip, the driver's existing location-reporting endpoint does one additional check: does this driver currently have a trip in ongoing status? If so, it pushes their new coordinates to that trip's rider over the same WebSocket connection used for match notifications. I didn't need a new pairing table — the Trip record already links rider and driver with a status field, so a single query answers 'who should receive this driver's position right now.' The main scaling concern is push frequency — every raw GPS ping currently triggers a push, which is fine at small scale but would need throttling, either by minimum distance moved or by a time cap, once you have many concurrent active trips generating pushes simultaneously."

What Was Proven, Concretely, in Testing

Confirmed that before a trip reached ongoing status, location pings behaved exactly as in Phase 1 — no push occurred. After transitioning the trip to ongoing via the Phase 5 state machine, three separate location updates (with independently chosen, varying coordinates) each triggered a distinct driver_location_update push, received live in an already-open rider WebSocket console, in the correct chronological order alongside the earlier driver_found and trip_status_updated events. This confirmed the full composed sequence — matching, status transition, and live tracking — working together correctly as one continuous flow, not just as isolated features.