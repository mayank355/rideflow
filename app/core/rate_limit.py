from fastapi import HTTPException, status
from app.core.geo_utils import redis_client

# Sliding-window-ish rate limiting using Redis INCR + EXPIRE. Not a true
# sliding window (that would need a sorted-set timestamp approach) — this
# is the simpler "fixed window" version: count resets entirely every
# window_seconds, rather than smoothly sliding. Good enough to stop abuse
# without the complexity of a precise sliding window.


def check_rate_limit(key: str, max_requests: int, window_seconds: int):
    """
    key: a unique string identifying WHO is being limited and for WHAT
    action, e.g. "ratelimit:location:driver_id" — different actions get
    independent limits, so hammering /location doesn't also block
    /go-online for the same user.

    Raises 429 if the limit is exceeded. Uses Redis INCR (atomic —
    concurrent requests can't race past each other and both "win") plus
    EXPIRE (only set on the FIRST request in a window, so the window
    has a fixed start, not one that resets on every request).
    """
    current_count = redis_client.incr(key)
    if current_count == 1:
        # First request in this window — start the countdown NOW.
        redis_client.expire(key, window_seconds)

    if current_count > max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: max {max_requests} requests per {window_seconds}s",
        )
