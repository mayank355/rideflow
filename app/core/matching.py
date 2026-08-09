from sqlalchemy.orm import Session

from app.core.geo_utils import redis_client, DRIVER_LOCATIONS_KEY
from app.models.driver import Driver


def find_nearby_drivers(latitude: float, longitude: float, radius_km: float = 5.0):
    """
    Step 1 (Redis): geospatial search for every driver within radius_km of
    the given point, sorted closest-first. This is the fast, indexed part —
    a single GEOSEARCH command against the shared geospatial structure.

    Returns a list of driver_id strings. Does NOT know or care whether
    these drivers are actually available — that's a Postgres concern,
    checked separately in the next step.
    """
    results = redis_client.geosearch(
        DRIVER_LOCATIONS_KEY,
        longitude=longitude,
        latitude=latitude,
        radius=radius_km,
        unit="km",
        sort="ASC",  # closest first
    )
    return results  # list of driver_id strings, in distance order


def find_best_available_driver(db: Session, latitude: float, longitude: float, radius_km: float = 5.0):
    """
    Step 2 (Postgres): cross-check Redis's geographic candidates against
    is_available=True. We only query Postgres for the small candidate list
    returned by Redis — NOT every driver in the system — keeping this cheap.

    Naive v1 policy: return the first available driver in the
    already-distance-sorted candidate list, i.e. the closest available one.
    Production systems (Uber-scale) instead solve a batched, fleet-wide
    assignment optimization problem — this is intentionally simpler.
    """
    candidate_ids = find_nearby_drivers(latitude, longitude, radius_km)
    if not candidate_ids:
        return None

    for driver_id in candidate_ids:
        driver = (
            db.query(Driver)
            .filter(Driver.id == driver_id, Driver.is_available == True)  # noqa: E712
            .first()
        )
        if driver:
            return driver  # first match = closest available driver

    return None  # nobody nearby is actually available
