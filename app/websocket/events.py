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


def driver_found_event(trip_id: uuid.UUID, driver_id: uuid.UUID) -> dict:
    """
    Sent to the RIDER the moment a driver is matched to their request.
    """
    return {
        "event": "driver_found",
        "trip_id": str(trip_id),
        "driver_id": str(driver_id),
    }
