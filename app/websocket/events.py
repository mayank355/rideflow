import uuid


def ride_assigned_event(trip_id: uuid.UUID, driver_id: uuid.UUID, rider_id: uuid.UUID,
                          pickup_latitude: float, pickup_longitude: float) -> dict:
    """
    Sent to the DRIVER the moment they're matched to a trip.
    Plain dict, not a Pydantic model — WebSocket sends raw JSON, and this
    keeps the event shape simple and explicit rather than routing it
    through another schema layer for a one-off message.
    """
    return {
        "event": "ride_assigned",
        "trip_id": str(trip_id),
        "rider_id": str(rider_id),
        "pickup_latitude": pickup_latitude,
        "pickup_longitude": pickup_longitude,
    }


def driver_found_event(trip_id: uuid.UUID, driver_id: uuid.UUID,
                         estimated_fare: float, eta_minutes: float) -> dict:
    """
    Sent to the RIDER the moment a driver is matched to their request.
    """
    return {
        "event": "driver_found",
        "trip_id": str(trip_id),
        "driver_id": str(driver_id),
        "estimated_fare": estimated_fare,
        "eta_minutes": eta_minutes,
    }


def trip_status_updated_event(trip_id: uuid.UUID, new_status: str) -> dict:
    """
    Sent to BOTH rider and driver whenever a trip transitions to a new
    status (ONGOING, COMPLETED, CANCELLED). Same payload shape for both
    recipients here, since "the trip's status changed" is symmetric
    information both sides need identically — unlike ride_assigned vs
    driver_found, which deliberately differ.
    """
    return {
        "event": "trip_status_updated",
        "trip_id": str(trip_id),
        "status": new_status,
    }


def driver_location_update_event(trip_id: uuid.UUID, latitude: float, longitude: float) -> dict:
    """
    Sent to the RIDER only, while a trip is ONGOING, every time the
    driver reports a new location. Deliberately minimal payload — just
    enough to move a marker on a map. This reuses the exact same Redis
    write path from Phase 1; the only new behavior is ALSO pushing to
    the rider when an active trip exists for this driver.
    """
    return {
        "event": "driver_location_update",
        "trip_id": str(trip_id),
        "latitude": latitude,
        "longitude": longitude,
    }
