What's protected now: location reporting, go-online/offline, ride requests, trip status updates, trip lookup, trip history, and route history all require a valid JWT and verify the caller actually owns/participates in that resource — not just "logged in as anyone."

Interview line: "Every protected endpoint does two checks, not one: authentication (is this a valid token?) and authorization (does this specific user own this specific resource?). A valid token alone isn't enough — a rider being logged in doesn't mean they can act on another rider's trip."

Right now, anyone can call POST /drivers/{any_id}/location and fake being any driver — there's no proof of identity. JWT auth fixes this: driver/rider signs up with a password (hashed, never stored in plain text), logs in, gets a signed token back, and must include that token on every future request. The server verifies the token's signature and identity on each call — like a wristband at a concert that proves you paid, without needing to re-check your ticket every time.

Interview line: "JWT is stateless auth — the server doesn't store session data, it just verifies a cryptographically signed token on each request. This matters at scale because any server instance can verify a token without needing shared session storage."

## 