from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.rider import Rider
from app.models.trip import Trip
from app.schemas.trip import RideRequest, TripOut
from app.core.matching import find_best_available_driver
from app.websocket.manager import driver_manager, rider_manager
from app.websocket.events import ride_assigned_event, driver_found_event

router = APIRouter(prefix="/rides", tags=["trips"])


@router.post("/request", response_model=TripOut)
async def request_ride(ride_in: RideRequest, db: Session = Depends(get_db)):
    """
    The core matching flow:
      1. Confirm the rider is real (Postgres read).
      2. Ask the matching engine for the closest available driver
         (Redis GEOSEARCH -> Postgres availability filter).
      3. Write the Trip row to Postgres — THIS is the exact moment the
         match becomes durable. Before this line, it's just a value in
         memory; after it, it survives a crash/restart.
      4. Push live notifications over WebSocket to both parties, if
         they're currently connected. This is a best-effort side effect —
         the trip is already durably saved regardless of whether either
         push actually reaches anyone.
    """
    rider = db.query(Rider).filter(Rider.id == ride_in.rider_id).first()
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    driver = find_best_available_driver(
        db,
        latitude=ride_in.pickup_latitude,
        longitude=ride_in.pickup_longitude,
    )
    if not driver:
        raise HTTPException(status_code=404, detail="No available drivers nearby")

    trip = Trip(
        rider_id=rider.id,
        driver_id=driver.id,
        pickup_latitude=ride_in.pickup_latitude,
        pickup_longitude=ride_in.pickup_longitude,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    # Notify the driver they've been assigned a ride
    await driver_manager.send_to(
        str(driver.id),
        ride_assigned_event(trip.id, driver.id, rider.id, trip.pickup_latitude, trip.pickup_longitude),
    )
    # Notify the rider a driver has been found
    await rider_manager.send_to(
        str(rider.id),
        driver_found_event(trip.id, driver.id),
    )

    return trip
