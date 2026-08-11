Phase 4: ETA + Fare Calculation
Real-world analogy first

Think about a taxi meter — the physical device that used to sit on dashboards. It didn't guess the fare, and it didn't need GPS or traffic data to give you a number when you got in: it just needed a starting point and a formula — base fare, plus a rate per kilometer, plus a rate per minute waiting in traffic. Simple, deterministic, no external dependencies.

That's exactly what we're building first: a straightforward, formula-based fare calculator. No traffic APIs, no machine learning, no external services. Given a pickup point and a driver's current location, we calculate a straight-line distance and multiply it by a rate structure — same principle as that old meter, just running in code instead of a mechanical dial.

Why this is a deliberately "simple by design" phase, and why that's fine to say in interviews

Everything before this phase involved a genuinely hard distributed-systems problem — geospatial indexing, hot/cold data splits, real-time push. ETA and fare calculation, in contrast, is comparatively simple math — and that's worth saying explicitly rather than dressing it up. The interesting engineering conversation here isn't "how do I calculate a fare," it's "what's the gap between what I built and what Uber actually needs," which we'll cover honestly.

The core problem: straight-line distance is a lie, and you should say so

Here's the thing to understand before writing any code: two points that are 2km apart in a straight line (as the crow flies) might require driving 5km on actual roads because of one-way streets, rivers, highways, or simply how city blocks are laid out. This is called the difference between Euclidean/Haversine distance and road-network distance.

We're going to calculate straight-line distance using the Haversine formula — the standard formula for distance between two lat/lng points on a sphere (Earth isn't flat, so simple Pythagorean distance would be wrong at any real-world scale). This gives a reasonable approximation, not the true driving distance.

What Uber actually uses instead: a routing engine (like OSRM, or their own internal system) that has an actual road network graph and computes real driving distance and time, accounting for turn restrictions, one-ways, and even live traffic conditions. That's a fundamentally different, much heavier system — external service calls, a road graph database, live traffic feeds.

Interview line: "I calculate straight-line distance using the Haversine formula for simplicity — it's fast and needs no external dependencies, but it's an approximation. Production ride-hailing systems use a routing engine with an actual road network graph to get real driving distance and account for traffic, which meaningfully changes both ETA and fare accuracy, especially in dense urban areas with irregular street layouts."

What we're exactly building in Phase 4
core/geo_utils.py extension — a Haversine distance function (pure math, no Redis/Postgres involved — this is a good moment to notice not everything belongs in every layer; this is just a calculation utility).
core/fare_calculator.py — takes distance (km) and returns a fare using a simple formula: base fare + (rate per km × distance). We'll also add a very basic time-of-day surge multiplier, since that's a real, common interview topic (dynamic pricing).
core/eta.py — takes distance and an assumed average speed, returns estimated minutes. Dead simple: time = distance / speed.
Wire these into the matching flow — when a Trip is created in POST /rides/request, calculate the driver's distance to the pickup point (using their Redis location) and include estimated_fare and eta_minutes in the response and in the WebSocket push events.
Add these two fields to the Trip model — so they're persisted, not just calculated on the fly and thrown away.

We're not building dynamic real-time traffic-aware pricing, and we're not integrating any mapping API — that's explicitly out of scope, and part of the value of this phase is being able to articulate exactly why, and what the upgrade path would look like.

## Two things worth understanding in this formula, since you'll be asked "explain Haversine" in interviews:

Why we convert to radians: all of Python's trig functions (sin, cos, atan2) expect angles in radians, not degrees — lat/lng coordinates are naturally in degrees, so this conversion is mandatory, not stylistic.
Why atan2 instead of a simpler asin: atan2 is numerically more stable for points that are very close together or nearly antipodal (opposite sides of the Earth) — it avoids precision errors that asin-based formulas can suffer from near the edges of their valid input range. You don't need to derive this from scratch in an interview, but knowing why atan2 shows up instead of asin demonstrates you understand the formula isn't just copy-pasted.

## RideFlow — Phase 4 Summary (ETA + Fare Calculation)
What Phase 4 Actually Was

Added deterministic, formula-based fare and ETA calculation to the matching flow. When a Trip is created, the driver's current Redis location and the rider's pickup point are used to compute a straight-line distance, which feeds both a fare formula and a simple ETA estimate — both persisted on the Trip record and pushed live to the rider over the WebSocket layer built in Phase 3.

The Real-World Analogy

An old-fashioned taxi meter: no GPS, no traffic data, no external service calls — just a starting charge, a rate per kilometer, and a mechanical dial turning as the car moves. Deterministic, dependency-free, "good enough" math. Phase 4 is that same principle in code: a plain formula, not a prediction model.

Core Concepts — Interview Ready
1. Which store the driver's position comes from — a direct callback to earlier phases
The Driver model in Postgres has never had lat/lng columns, by design since Phase 1. So calculating distance at match time means reading the driver's current position from Redis via get_driver_location(), never Postgres.
Interview line: "Distance calculation reads the driver's live position from Redis — Postgres never had location data to begin with, so there was no ambiguity about which store to query."
2. Haversine formula — straight-line distance, and its explicit limitation
Haversine computes great-circle distance between two lat/lng points on a sphere, accounting for Earth's curvature (a flat Pythagorean calculation would be measurably wrong at real-world scale).
The critical caveat, stated proactively, not hidden: this is straight-line ("as the crow flies") distance, not actual driving distance. Two points 2km apart in a straight line might require 5km of real road travel due to one-ways, rivers, highway routing, or city block layout.
What production systems use instead: a routing engine with an actual road-network graph (e.g. OSRM), which computes real driving distance and time, accounting for turn restrictions and live traffic — a fundamentally heavier system involving external routing calls and a maintained road graph.
Interview line: "I use Haversine for straight-line distance because it's fast and dependency-free, but it's an approximation — production ride-hailing systems use a routing engine with a real road network graph, which changes both the ETA and fare accuracy substantially, especially in dense urban areas with irregular streets."
Why atan2 and not asin: numerically more stable for points that are very close together or near-antipodal — avoids precision errors asin-based formulas can hit near the edges of their valid input range.
3. Fare calculation — simple formula, explicitly simplified surge
fare = base_fare + (rate_per_km × distance), with a flat multiplier applied during two hardcoded "peak" time windows.
The honest limitation: real surge pricing (Uber's actual approach) is computed per small geographic zone, driven by the live ratio of active ride requests to available drivers in that zone, recalculated continuously — not a fixed clock schedule. This implementation demonstrates the concept of dynamic pricing without building the real demand-supply computation, which would require real-time aggregation across all active requests and drivers per geographic cell.
Interview line: "My surge logic is a placeholder — a fixed time-of-day multiplier. Real surge pricing is a live function of local supply and demand per geographic zone, recalculated continuously, which is a meaningfully harder aggregation problem than a clock check."
4. ETA calculation — same honesty about its limitation
time = distance / assumed_average_speed, converted to minutes. A single flat speed constant regardless of actual road conditions, traffic, or route complexity.
Interview line: "ETA here assumes constant speed — a real system would use a routing engine's turn-by-turn estimate informed by live traffic data, which is a genuinely different and heavier computation."
5. Why create_all() couldn't handle this phase's schema change — Alembic's actual moment
Back in Phase 1, it was noted that Base.metadata.create_all() only creates tables that don't yet exist — it cannot alter an existing table's columns.
Adding estimated_fare and eta_minutes to the already-existing trips table required manually dropping and recreating the table, since there was no real data worth preserving yet.
The critical point to say out loud in an interview: "In a production system with live trip data, dropping the table would be catastrophic — this is exactly the scenario where you'd write an Alembic migration to add columns without touching existing rows. I used a manual drop here only because it was pre-production test data with nothing to lose." This demonstrates you understand when the tool choice matters, not just that the tool exists.
6. Distinct WebSocket event payloads for driver vs rider — not identical, on purpose
The driver receives ride_assigned — pickup location and rider id, because a driver needs to know where to go, not the fare/ETA math.
The rider receives driver_found — now including estimated_fare and eta_minutes, because that's the information a rider actually needs before the trip starts.
Interview line: "The two WebSocket events carry different payloads because the two recipients need different information — this isn't the same message broadcast to both sides, it's two purpose-built payloads for two different roles in the same event."
7. Calculation lives in pure functions, decoupled from any datastore
haversine_distance_km, calculate_fare, and calculate_eta_minutes take plain numbers in, return plain numbers out — no Redis client, no Postgres session, no I/O at all inside them.
Why this matters: these functions are trivially unit-testable in isolation (feed known coordinates, assert the expected distance) without needing a running database or Redis instance — a real, concrete testability argument, not an abstract one.
One-Line Tradeoffs (memorize these)
Haversine vs routing-engine distance: gain zero external dependencies and fast computation, lose real driving-distance accuracy — a meaningful gap in dense or irregular road networks.
Fixed time-of-day surge vs live demand/supply surge: gain simplicity and zero real-time aggregation cost, lose actual responsiveness to real congestion/demand imbalances.
Manual table drop vs Alembic migration: gain speed for pre-production iteration, lose safety the moment real user data exists — the exact line where the "quick" approach becomes unacceptable.
What to Say If Asked "Walk Me Through Fare/ETA" in an Interview

"When a trip is matched, I pull the driver's current position from Redis and calculate straight-line distance to the pickup point using the Haversine formula — I'm explicit that this is an approximation, not real driving distance, since production systems use a routing engine with an actual road graph for that. Fare is a simple base-plus-per-kilometer formula with a placeholder time-of-day surge multiplier — real surge pricing is a live supply-and-demand computation per geographic zone, which I didn't build here, but I understand the gap. Both values get persisted on the Trip record and pushed to the rider over the WebSocket layer, using a distinct event payload from what the driver receives, since each side needs different information."

What Was Proven, Concretely, in Testing

Verified the fare/ETA math by hand against known test coordinates (~3.15km apart): fare calculation and ETA matched the expected formula output within rounding. Confirmed the is_peak_hour check correctly did NOT apply the surge multiplier at an 11:39 AM UTC timestamp, outside the defined peak windows. Verified the two WebSocket events are genuinely distinct — the driver's open connection received ride_assigned (pickup details, no fare), while a separately connected rider received driver_found (correctly including estimated_fare and eta_minutes) for the same trip, proving the dual-payload design works as intended, not just in theory.