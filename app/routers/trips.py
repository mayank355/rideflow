from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from app.database import get_db
from app.models.rider import Rider
from app.models.driver import Driver
from app.models.trip import Trip, TripStatus
from app.models.trip_location_log import TripLocationLog
from app.schemas.trip import RideRequest, TripOut, TripStatusUpdate
from app.core.matching import find_best_available_driver
from app.core.geo_utils import get_driver_location, haversine_distance_km
from app.core.fare_calculator import calculate_fare
from app.core.eta import calculate_eta_minutes
from app.core.trip_state_machine import is_valid_transition
from app.core.location_throttle import clear_trip_tracking
from app.websocket.manager import driver_manager, rider_manager
from app.websocket.events import ride_assigned_event, driver_found_event, trip_status_updated_event

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

    # Read the driver's CURRENT position from Redis (never Postgres —
    # Postgres has no location data, by design since Phase 1) to compute
    # a straight-line distance from driver to pickup point.
    driver_location = get_driver_location(str(driver.id))
    if driver_location:
        distance_km = haversine_distance_km(
            driver_location["latitude"], driver_location["longitude"],
            ride_in.pickup_latitude, ride_in.pickup_longitude,
        )
    else:
        # Extremely unlikely here (find_best_available_driver only
        # returns drivers GEOSEARCH found, meaning they have a location),
        # but defensive fallback avoids a crash if Redis data vanished
        # between the search and this read.
        distance_km = 0.0

    estimated_fare = calculate_fare(distance_km)
    eta_minutes = calculate_eta_minutes(distance_km)

    trip = Trip(
        rider_id=rider.id,
        driver_id=driver.id,
        pickup_latitude=ride_in.pickup_latitude,
        pickup_longitude=ride_in.pickup_longitude,
        estimated_fare=estimated_fare,
        eta_minutes=eta_minutes,
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
        driver_found_event(trip.id, driver.id, trip.estimated_fare, trip.eta_minutes),
    )

    return trip


@router.patch("/{trip_id}/status", response_model=TripOut)
async def update_trip_status(trip_id: uuid.UUID, update: TripStatusUpdate, db: Session = Depends(get_db)):
    """
    Transitions a trip to a new status, enforcing the state machine —
    e.g. a COMPLETED trip can never move to any other status, and a
    REQUESTED trip can't jump straight to COMPLETED without going
    through ONGOING and PAYMENT_PENDING first.

    Side effect: when a trip becomes ONGOING, the driver is busy with
    this specific rider, so is_available flips to False. The driver
    STAYS unavailable through PAYMENT_PENDING (the ride physically ended,
    but payment hasn't settled yet — mirrors real ride-hailing apps,
    where a driver isn't freed until payment is confirmed, not the
    instant the ride ends). Only COMPLETED or CANCELLED frees the driver.
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    if not is_valid_transition(trip.status, update.new_status):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition trip from {trip.status.value} to {update.new_status.value}",
        )

    trip.status = update.new_status

    driver = db.query(Driver).filter(Driver.id == trip.driver_id).first()
    if driver:
        if update.new_status == TripStatus.ONGOING:
            driver.is_available = False
        elif update.new_status in (TripStatus.COMPLETED, TripStatus.CANCELLED):
            driver.is_available = True
            clear_trip_tracking(str(trip.id))

    db.commit()
    db.refresh(trip)

    event = trip_status_updated_event(trip.id, trip.status.value)
    await driver_manager.send_to(str(trip.driver_id), event)
    await rider_manager.send_to(str(trip.rider_id), event)

    return trip


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Fallback lookup path for a single trip's current state — useful if a
    rider/driver's app wasn't connected via WebSocket when a push
    happened (pushes are best-effort, established in Phase 3), so they
    can just ask directly instead of waiting for one that already passed.
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.get("/history/{rider_id}", response_model=list[TripOut])
def get_trip_history(rider_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    All past trips for a rider, most recent first. Kept unpaginated for
    now — fine at small scale, but a rider with thousands of trips would
    need cursor-based pagination here in a real system, not offset-based
    (offset pagination degrades badly at large offsets since the database
    still has to scan and discard all skipped rows).
    """
    trips = (
        db.query(Trip)
        .filter(Trip.rider_id == rider_id)
        .order_by(Trip.created_at.desc())
        .all()
    )
    return trips


@router.get("/{trip_id}/route")
def get_trip_route(trip_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Full recorded path for a trip, in chronological order — the data
    needed to draw/replay the actual route driven, distinct from the
    single current position Redis holds while a trip is live.
    """
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    points = (
        db.query(TripLocationLog)
        .filter(TripLocationLog.trip_id == trip_id)
        .order_by(TripLocationLog.recorded_at.asc())
        .all()
    )
    return [
        {"latitude": p.latitude, "longitude": p.longitude, "recorded_at": p.recorded_at}
        for p in points
    ]


def find_active_trip_for_driver(db: Session, driver_id: str):
    """
    Looks up whether this driver currently has a trip in ONGOING status.

    Notice this doesn't need a separate rider<->driver pairing table —
    Trip already IS that pairing, with a status field telling us whether
    it's currently active. This is the same table built in Phase 2,
    reused here for a new purpose.
    """
    return (
        db.query(Trip)
        .filter(Trip.driver_id == driver_id, Trip.status == TripStatus.ONGOING)
        .first()
    )
