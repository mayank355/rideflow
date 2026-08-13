from typing import Dict, Tuple
from app.core.geo_utils import haversine_distance_km

# In-memory, per-trip record of the last position we actually PUSHED to a
# rider (not the last position written to Redis — every ping still writes
# to Redis regardless of throttling, since matching/ETA still needs fresh
# data there). Ephemeral by design, same reasoning as the WebSocket
# ConnectionManager: if the server restarts, we just push the next ping
# unconditionally (treated as "first push"), which is harmless.
_last_pushed_location: Dict[str, Tuple[float, float]] = {}

# Minimum movement, in kilometers, required before pushing another
# location update for the same trip. ~0.015km = 15 meters — small enough
# to feel responsive, large enough to skip pushes from GPS jitter or a
# car stopped at a light.
MIN_PUSH_DISTANCE_KM = 0.015


def should_push_location(trip_id: str, latitude: float, longitude: float) -> bool:
    """
    Returns True if this location differs enough from the last pushed
    position for this trip to be worth sending. Always True for the
    first location seen for a given trip.

    This is deliberately simple — a real system might also add a time-
    based cap (e.g. "at most once every N seconds regardless of distance")
    to handle bursty updates. Distance-only throttling is the cheaper,
    single-factor version of that idea, sufficient to demonstrate the
    concept without over-building it.
    """
    last = _last_pushed_location.get(trip_id)
    if last is None:
        _last_pushed_location[trip_id] = (latitude, longitude)
        return True

    last_lat, last_lon = last
    moved_km = haversine_distance_km(last_lat, last_lon, latitude, longitude)

    if moved_km >= MIN_PUSH_DISTANCE_KM:
        _last_pushed_location[trip_id] = (latitude, longitude)
        return True

    return False


def clear_trip_tracking(trip_id: str):
    """
    Called when a trip ends (completed/cancelled) to avoid this dict
    growing forever with entries for trips that will never be pushed to
    again. Small but real — without this, _last_pushed_location leaks
    memory indefinitely as trips accumulate over the app's lifetime.
    """
    _last_pushed_location.pop(trip_id, None)
