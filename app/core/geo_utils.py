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
