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
from app.core.auth_deps import get_current_driver, get_current_rider, get_current_principal
from app.core.rate_limit import check_rate_limit
from app.websocket.manager import driver_manager, rider_manager
from app.websocket.events import ride_assigned_event, driver_found_event, trip_status_updated_event

router = APIRouter(prefix="/rides", tags=["trips"])


def _require_trip_participant(trip: Trip, current_driver: Driver = None, current_rider: Rider = None):
    """
    Ownership check for trip-scoped actions: the caller must be either
    the driver OR the rider actually on this specific trip — not just
    any authenticated user. Without this, any logged-in rider could
    mark ANY trip completed, or read ANY trip's route, not just their own.
    """
    if current_driver and str(trip.driver_id) == str(current_driver.id):
        return
    if current_rider and str(trip.rider_id) == str(current_rider.id):
        return
    raise HTTPException(status_code=403, detail="Not a participant on this trip")


@router.post("/request", response_model=TripOut)
async def request_ride(
    ride_in: RideRequest,
    db: Session = Depends(get_db),
    current_rider: Rider = Depends(get_current_rider),
):
    """
    The core matching flow. NOW REQUIRES RIDER AUTH: the caller must be
    logged in as the exact rider_id being requested for — without this,
    any authenticated rider could request rides on behalf of another
    rider's account (and have THEIR payment method/history attached).
    """
    if str(current_rider.id) != str(ride_in.rider_id):
        raise HTTPException(status_code=403, detail="Cannot request a ride on behalf of another rider")

    # Ride requests are a legitimately rare action (a few per hour at
    # most for any real rider) -- max 5 per 60 sec is generous headroom
    # for retries/misclicks while still blocking a scripted spam attack
    # that could otherwise flood the matching engine with fake requests.
    check_rate_limit(f"ratelimit:ride_request:{ride_in.rider_id}", max_requests=5, window_seconds=60)

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
async def update_trip_status(
    trip_id: uuid.UUID,
    update: TripStatusUpdate,
    db: Session = Depends(get_db),
    principal=Depends(get_current_principal),
):
    """
    Transitions a trip to a new status, enforcing the state machine.
    NOW REQUIRES AUTH: caller must be either the driver or rider actually
    ON this trip — not just any authenticated user. A stranger with a
    valid token should never be able to mark someone else's trip
    completed or cancel it.
    """
    role, user = principal

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    _require_trip_participant(
        trip,
        current_driver=user if role == "driver" else None,
        current_rider=user if role == "rider" else None,
    )

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
def get_trip(trip_id: uuid.UUID, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """
    Fallback lookup path for a single trip's current state. NOW REQUIRES
    AUTH + participant check — a trip's fare, pickup location, and
    status are private to the two people involved in it.
    """
    role, user = principal
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    _require_trip_participant(
        trip,
        current_driver=user if role == "driver" else None,
        current_rider=user if role == "rider" else None,
    )
    return trip


@router.get("/history/{rider_id}", response_model=list[TripOut])
def get_trip_history(
    rider_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_rider: Rider = Depends(get_current_rider),
):
    """
    All past trips for a rider. NOW REQUIRES RIDER AUTH + ownership — a
    rider can only view their OWN trip history, never another rider's.
    """
    if str(current_rider.id) != str(rider_id):
        raise HTTPException(status_code=403, detail="Cannot view another rider's trip history")

    trips = (
        db.query(Trip)
        .filter(Trip.rider_id == rider_id)
        .order_by(Trip.created_at.desc())
        .all()
    )
    return trips


@router.get("/{trip_id}/route")
def get_trip_route(trip_id: uuid.UUID, db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """
    Full recorded path for a trip. NOW REQUIRES AUTH + participant check
    — route history is exactly the kind of data (where someone actually
    went) that must never be readable by an arbitrary authenticated user.
    """
    role, user = principal
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    _require_trip_participant(
        trip,
        current_driver=user if role == "driver" else None,
        current_rider=user if role == "rider" else None,
    )

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
