import os
import redis

REDIS_URL = os.getenv("REDIS_URL")

# Single Redis client connection, reused across the app
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# The single key under which ALL drivers' locations live in one geospatial structure.
# This is what makes GEOSEARCH later able to query across every driver at once.
DRIVER_LOCATIONS_KEY = "driver_locations"


def update_driver_location(driver_id: str, longitude: float, latitude: float):
    """
    Writes/overwrites a driver's current position into Redis.

    GEOADD note: order is (longitude, latitude) — NOT (latitude, longitude).
    Getting this backwards silently puts drivers in the wrong hemisphere,
    with no error thrown, so double check every call site.

    Calling this again for the same driver_id simply overwrites their
    previous position — Redis keeps no history here, by design.
    """
    redis_client.geoadd(DRIVER_LOCATIONS_KEY, (longitude, latitude, driver_id))


def get_driver_location(driver_id: str):
    """
    Returns the driver's last known (longitude, latitude), or None if
    they've never reported a location.
    """
    result = redis_client.geopos(DRIVER_LOCATIONS_KEY, driver_id)
    if not result or result[0] is None:
        return None
    longitude, latitude = result[0]
    return {"longitude": float(longitude), "latitude": float(latitude)}


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Straight-line ("as the crow flies") distance between two lat/lng
    points, in kilometers, accounting for Earth's curvature.

    IMPORTANT LIMITATION, stated explicitly: this is NOT actual driving
    distance. Two points 2km apart in a straight line might require 5km
    of actual road travel due to one-ways, rivers, highways, or how city
    blocks are laid out. Production systems (Uber, etc.) use a routing
    engine with a real road-network graph (e.g. OSRM) to get true driving
    distance and account for live traffic — a fundamentally heavier
    system involving external routing calls and a road graph database.

    We use Haversine here because it's fast, needs zero external
    dependencies, and is a reasonable approximation for a project at
    this stage — but the gap between this and real driving distance is
    real and worth naming, not hiding.
    """
    import math

    R = 6371.0  # Earth's radius in km

    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)

    d_lat = lat2_rad - lat1_rad
    d_lon = lon2_rad - lon1_rad

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
