Rate limiting stops one client from hammering an endpoint — think of it like a bouncer capping how many times the same person can enter a club per minute, even if each individual entry is otherwise legitimate. We'll use Redis (already in your stack) to track request counts per user per time window, and block once they exceed a limit. This depends on auth existing (done) since we key limits by the authenticated user's id, not just IP — more precise than IP-based limiting, which breaks down behind shared NATs/proxies.

Interview line: "I rate-limit per authenticated user id rather than per IP, since IP-based limiting is unreliable behind NAT or corporate proxies where many legitimate users share one IP — keying by user id ties the limit to actual identity."

What it does: Redis-backed fixed-window rate limiting. Location updates capped at 20 per 10 seconds per driver; ride requests capped at 5 per 60 seconds per rider. Uses Redis INCR (atomic — no race condition where two concurrent requests both slip through) + EXPIRE (only set on the first request in a window).

Interview line: "I used Redis INCR for the counter because it's atomic — under concurrent load, two simultaneous requests can't both read the same count and both think they're under the limit. I key limits per authenticated user id, not per IP, since IP-based limiting breaks down behind shared NATs or corporate proxies."


## part_3

State machine — every valid transition explicitly allowed, every invalid one explicitly blocked (including both terminal states rejecting all outgoing transitions via a loop)
Fare/ETA — formula correctness verified against hand-calculated expected values, plus a real-world sanity check (Delhi→Gurgaon distance) and boundary testing (10 AM peak-hour edge)
Matching — Redis called with exactly the right params (mocked, no live connection), and critically: a test proving the engine correctly skips an unavailable closer driver and picks the next available one — not just "does it return something"
Auth — password hash uniqueness (salting), tampered-token rejection, wrong-secret rejection, and expired-token rejection — all via real cryptographic operations, not mocked

Interview line: "These aren't blanket coverage — each test targets a specific correctness property I can defend: the matching test proves availability filtering actually skips the wrong candidate, not just returns any result; the auth tests prove tampering and expiry are cryptographically enforced, not just present in the token format."


## part_4

Right now, your app's only output is uvicorn's default request logs (INFO: 172.18.0.1:xxxx - "GET /health HTTP/1.1" 200 OK) — fine for a human staring at a terminal, useless for a real production system where logs get shipped to something like Datadog/ELK and need to be searchable, filterable JSON, not plain text. We'll add structured JSON logging with a request ID (to trace one request across multiple log lines) and user ID (once authenticated) attached to every log entry.

Interview line: "Plain-text logs are fine for local debugging but don't scale operationally — you can't easily query 'show me every log line for this specific failing request' across a fleet of instances. Structured JSON logs with a request ID let you do exactly that in any log aggregation tool."

What it does: every request now logs one JSON line with request_id (unique per request, also returned as an X-Request-ID response header), method, path, status_code, duration_ms. Uvicorn's default plain-text access logs are replaced with this JSON output.

Interview line: "Every request gets a unique ID attached at the middleware level and returned in the response header — if a rider reports a bug, I can ask for that ID and pull every log line for that exact request instantly, instead of correlating by timestamp guesswork across possibly-interleaved concurrent requests."