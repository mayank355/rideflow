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