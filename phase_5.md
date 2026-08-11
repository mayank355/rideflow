 ## Phase 5: Trip Lifecycle — Status Transitions + Trip History
Real-world analogy first

Think about tracking a package delivery. It doesn't just have two states — "ordered" and "delivered." It moves through a sequence: order placed → picked up → out for delivery → delivered. Each stage is a deliberate transition, and critically, you can't skip stages — a package can't go from "order placed" straight to "delivered" without passing through the middle states, and once it's "delivered," it can't go back to "out for delivery." That's a state machine — a defined set of states with defined, valid transitions between them, and everything else forbidden.

Right now, every Trip in RideFlow gets created with status = "requested" and then... nothing ever changes it. There's no way to mark a trip as picked up, ongoing, or completed. Phase 5 builds that lifecycle — the actual sequence a real ride goes through — plus a way for a rider to look back and see their past trips, the same way you can open a delivery app and see your order history.

Why this matters beyond just "adding more endpoints"

This is where state machine validity becomes a real engineering concern, not just a CRUD update. If you allow any status to be set to any other status via a naive PATCH endpoint, you get bugs like a completed trip being changed back to requested, or a cancelled trip suddenly becoming ongoing — nonsensical states that corrupt your data's meaning. Interviewers care about this because "state machine correctness" is a recurring theme in backend systems — order processing, payment flows, trip lifecycles, CI/CD pipelines — anywhere something moves through a defined sequence of stages.

The valid transitions we'll enforce
REQUESTED → ONGOING → COMPLETED
REQUESTED → CANCELLED
ONGOING → CANCELLED   (e.g., driver has an emergency mid-trip)

Notice what's not allowed: COMPLETED → anything (a finished trip is final), CANCELLED → anything (also final), and you can't skip REQUESTED straight to COMPLETED (skipping the actual ride happening).

What "driver picks up rider" actually means in our system

When a trip moves from REQUESTED to ONGOING, that's the real-world moment the driver has physically arrived and started the ride. This is also the natural point where the driver's is_available flag should flip back to false in Postgres — they're now busy with this specific rider, so they shouldn't show up in future GEOSEARCH matches for other riders. This connects directly back to Phase 2's matching logic: availability isn't just set once at "go online," it needs to be actively managed across the trip lifecycle, and this is the first place we actually do that.

Symmetrically, when a trip moves to COMPLETED (or CANCELLED), the driver becomes available again — is_available flips back to true, ready to be matched with the next rider.

What we're exactly building in Phase 5
A state transition map (core/trip_state_machine.py) — a simple dictionary defining which status can move to which other statuses, plus a function that validates a requested transition against it.
PATCH /trips/{trip_id}/status — an endpoint that takes a new status, validates the transition is legal using the state machine, updates the Trip row, and — critically — flips the matched driver's is_available flag as a side effect when appropriate.
WebSocket push on status change — both rider and driver get notified live when a trip's status changes, using the same ConnectionManager infrastructure from Phase 3. New event type: trip_status_updated.
GET /trips/history/{rider_id} — returns all past trips for a given rider, ordered most-recent-first. This is a straightforward Postgres query, but it's the first place we do a "get many records for one user" pattern, which is worth doing properly (pagination consideration, even if we keep it simple for now).
GET /trips/{trip_id} — a simple lookup for one trip by id, useful for a rider/driver polling a trip's current state if they weren't connected via WebSocket when a push happened (a fallback path, since we established pushes are best-effort/fire-and-forget in Phase 3).

We're not building actual GPS-based "trip in progress" tracking (continuously updating a driver's position during an active trip and pushing that to the rider) — that's a natural Phase 6 extension, since it would reuse the exact same Redis location + WebSocket push mechanisms you already have, just triggered continuously instead of once.

Worth pausing on that comment I wrote — it's a real interview-relevant observation: ride_assigned and driver_found are asymmetric because the two parties need different information at match time, but trip_status_updated is symmetric because "the status changed" is the same fact for both sides. Recognizing when payloads should differ versus when they should be identical is a design judgment call, not an accident.

## Two design notes worth internalizing before testing:

Why driver is looked up again inside update_trip_status — the trip object only has driver_id (a UUID), not the actual Driver row. To flip is_available, we need to fetch that row fresh, mutate it, and let the same db.commit() save both changes (trip status + driver availability) atomically in one transaction — either both changes save, or if something fails, neither does. This is a real, meaningful use of a single database transaction, not just habit.
The pagination comment in get_trip_history — I flagged offset-based pagination's weakness proactively. If asked "how would you paginate this at scale" in an interview, you now have the answer ready: cursor-based (e.g., "give me trips created before this timestamp/id") rather than offset-based ("skip the first 10,000 rows"), because offset pagination forces the database to still scan and discard every skipped row, getting progressively slower as the offset grows.

## problem 

The actual problem right now: there is no way for a real driver to ever become available in your system except by someone manually running SQL. If you handed RideFlow to an actual user tomorrow, a driver could register, report their location, and then... be permanently stuck as is_available = false forever, because the only path to true is a database console command they'd never have access to. That's not a missing nice-to-have — it's a missing core feature. Registration without a way to "go online" is like a store that has no way to unlock its front door.

Why it's small to add, though: you already have every piece needed. The pattern is identical to the location-update endpoint from Phase 1 — look up the driver, flip one field, commit. It's maybe 15 lines of code, reusing infrastructure you already built.

Why it's worth doing before the Phase 5 summary specifically: right now your interview story has an honest gap — "how does a driver become available?" would currently have to be answered with "I ran SQL manually," which is a weak answer in an interview. Adding this closes that gap cleanly, and it directly complements the state machine work from this phase (driver availability is now managed both by trip lifecycle and by an explicit online/offline toggle — which is exactly how real systems work).

## RideFlow — Phase 5 Summary (Trip Lifecycle, State Machine, Go-Online/Offline)
What Phase 5 Actually Was

Built the real trip lifecycle: a state machine enforcing valid status transitions, live WebSocket pushes on every status change, trip history lookup, and — critically — replaced the manual psql workaround used since Phase 2 with real go-online/go-offline endpoints, closing a genuine gap in the system rather than leaving it as a permanent test-only crutch.

The Real-World Analogy

Package delivery tracking: order placed → picked up → out for delivery → delivered. You can't skip stages, and once "delivered," it can't revert to "out for delivery." That's a state machine — a defined set of states with defined, valid transitions, everything else forbidden. RideFlow's trip status now works the same way: REQUESTED → ONGOING → COMPLETED, with CANCELLED reachable from either non-terminal state, and both COMPLETED/CANCELLED being final.

Core Concepts — Interview Ready
1. Why a state machine, not a free-form status field
Without enforced transitions, a naive update endpoint would let a COMPLETED trip silently become ONGOING again, or let a trip skip straight from REQUESTED to COMPLETED without the ride ever happening — both are data corruption, not just "unusual" states.
VALID_TRANSITIONS is a single dictionary mapping each status to the set of statuses it's legally allowed to move to; COMPLETED and CANCELLED map to empty sets — terminal, no way out.
Interview line: "Trip status is a state machine, not a free-form field. I validate every transition against an explicit allowed-transitions map before applying it, so a completed trip can never be silently reopened and a trip can't skip the actual ride."
2. The side effect of a status transition — availability is actively managed, not set once
Moving to ONGOING flips the matched driver's is_available to false in Postgres — they're now busy with this specific rider and must stop appearing in future GEOSEARCH matches.
Moving to COMPLETED or CANCELLED flips it back to true — freeing the driver for the next match.
Why this is done inside the same database transaction as the status update: both the trip's status and the driver's availability are updated, then committed together with one db.commit(). Either both changes save, or — if something fails first — neither does. This prevents a broken intermediate state like "trip says ongoing, but driver still shows available."
Interview line: "Availability isn't just set once at 'go online' — it's actively managed across the trip lifecycle. I update both the trip's status and the driver's availability in the same transaction so they can never drift out of sync."
3. Symmetric vs asymmetric WebSocket event payloads — a design judgment call
ride_assigned (driver) and driver_found (rider) deliberately carry different fields, because the two parties need different information at match time (driver needs pickup location; rider needs fare/ETA).
trip_status_updated, introduced this phase, carries the same payload to both sides — because "the trip's status changed" is symmetric information both parties need identically.
Interview line: "Not every event should have the same shape for every recipient — I differentiate payloads when the two sides need different information, and keep them identical when the information itself is symmetric. That's a deliberate per-event decision, not a fixed template."
4. Why the manual psql workaround was a real gap, not just a testing inconvenience
From Phase 2 through Phase 4, the only way to mark a driver is_available = true was running raw SQL by hand — meaning a real driver, using a real app, would have had no way to ever go online in the system as it stood.
This was explicitly flagged as backlog from the very start of the project and closed out in this phase with two real endpoints: POST /drivers/{driver_id}/go-online and /go-offline, doing exactly what the manual UPDATE statements did, but as a real, callable mechanism a driver's app would actually use.
Interview line: "Early on I used direct SQL to flip a driver's availability during testing — that's not a real mechanism, just a stand-in for an endpoint that didn't exist yet. I made sure to close that gap before considering matching 'done,' since a system where a driver can never actually go online isn't functionally complete, regardless of how good the matching logic underneath is."
A subtlety worth stating: go-online only touches Postgres (is_available). It deliberately does NOT touch Redis — a driver could go online but never report a location, in which case GEOSEARCH simply won't find them. This is correct: availability and location are separate concerns tracked in separate stores, and both need to be true for a driver to actually be matchable.
5. GET /trips/{trip_id} — a fallback path, given Phase 3's known limitation
WebSocket pushes were established in Phase 3 as best-effort/fire-and-forget — no retry, no guaranteed delivery. If a rider's app wasn't connected when a push happened, they'd simply never receive it.
GET /trips/{trip_id} gives any client a way to directly ask "what's this trip's current state right now" instead of depending entirely on a push that may have already come and gone.
Interview line: "Since WebSocket pushes aren't guaranteed, I added a direct lookup endpoint as a fallback — a client that missed a push, or wasn't connected yet, can just ask for current state instead of being stuck waiting for a notification that already happened."
6. Trip history — unpaginated for now, with the real limitation named
GET /trips/history/{rider_id} returns all of a rider's trips, ordered most-recent-first, with no pagination.
The honest limitation: fine at small scale, but a rider with thousands of trips would need pagination — and specifically cursor-based, not offset-based, because offset pagination (OFFSET 10000 LIMIT 20) still forces the database to scan and discard every skipped row, getting progressively slower as the offset grows. Cursor-based pagination (e.g., "give me trips created before this timestamp") avoids that entirely.
Interview line: "This endpoint isn't paginated yet, which is fine at current scale — but I'd use cursor-based pagination rather than offset-based if this needed to scale, since offset pagination degrades as the skipped-row count grows, while a cursor on created_at doesn't."
7. The honest gap that remains: payment
In a real ride-hailing system, ending a trip does not immediately mean "completed." Real flows typically insert an intermediate state (e.g. PAYMENT_PENDING) between the ride physically ending and the trip being marked done, because payment processing is an external, asynchronous call that can fail or take time — and a driver often only becomes available again once payment is confirmed, not the instant the ride ends.
RideFlow's state machine currently collapses "ride ended" and "payment settled" into a single COMPLETED transition — a deliberate simplification, not an oversight, since building real payment integration (gateway APIs, async webhooks, retry/idempotency logic to avoid double-charging) is a substantial separate subsystem, out of scope for this project's focus on real-time matching and geospatial systems.
Interview line: "I collapsed trip-completion and payment-completion into one transition for simplicity. In production these are separate concerns — I'd model an additional PAYMENT_PENDING state between ONGOING and COMPLETED, with driver availability tied to the final settled state, not the moment the ride physically ends."
One-Line Tradeoffs (memorize these)
Explicit state machine vs free-form status updates: gain guaranteed data integrity for trip lifecycle, lose the flexibility of arbitrary status changes — a deliberate and correct restriction, not a limitation to apologize for.
Same-transaction driver + trip update: gain atomicity (both change or neither does), lose nothing meaningful at this scale — a clearly correct choice.
Real go-online endpoint vs manual psql: gain a functionally complete system a real user could actually operate, at the cost of ~15 extra lines of code — an easy, necessary trade, not really a tradeoff at all.
Unpaginated trip history now vs cursor pagination later: gain simplicity today, lose scalability at high trip-count — explicitly deferred, with the correct upgrade path already identified.
What to Say If Asked "Walk Me Through Your Trip Lifecycle" in an Interview

"Trip status is a state machine — requested moves to ongoing or cancelled, ongoing moves to completed or cancelled, and both completed and cancelled are terminal with no way out. Every transition is validated against an explicit map before being applied, so the database can never end up in a nonsensical state like a completed trip becoming ongoing again. Each valid transition also updates the driver's availability in the same transaction — busy while ongoing, free again once the trip ends — so those two facts can never drift out of sync. I also closed a real gap from earlier phases: driver availability used to only be testable through raw SQL, which meant a real driver would have had no way to actually go online. I built real go-online and go-offline endpoints to fix that, since a system where the core actor can't actually activate themselves isn't functionally complete, no matter how good the matching underneath is."

What Was Proven, Concretely, in Testing

Confirmed the state machine rejects an invalid transition (requested → completed directly) with a clear 400 error naming the invalid transition explicitly. Confirmed the valid path (requested → ongoing → completed) succeeds, with the driver's is_available flag correctly flipping to false on ongoing and back to true on completed, verified directly via database query at each step. Confirmed WebSocket pushes fire correctly on every status transition, arriving live in an already-open console connection. Replaced every remaining manual psql availability update with the new go-online endpoint and re-ran the full flow successfully with zero manual SQL involved. Confirmed trip history correctly returns a list (supporting multiple trips per rider) with the completed trip's full data intact, including fare and ETA persisted from Phase 4.