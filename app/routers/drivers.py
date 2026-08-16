from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.driver import Driver
from app.models.trip_location_log import TripLocationLog
from app.schemas.driver import DriverCreate, DriverOut, LocationUpdate
from app.core.geo_utils import update_driver_location
from app.core.location_throttle import should_push_location
from app.core.auth_deps import get_current_driver
from app.core.rate_limit import check_rate_limit
from app.routers.trips import find_active_trip_for_driver
from app.websocket.manager import rider_manager
from app.websocket.events import driver_location_update_event

router = APIRouter(prefix="/drivers", tags=["drivers"])


def _require_self(driver_id: str, current_driver: Driver):
    """
    Ownership check: the authenticated driver must BE the driver_id in
    the URL. Without this, any logged-in driver could report location,
    go online/offline, etc. AS a different driver — authentication alone
    (proving who you are) isn't authorization (proving you're allowed to
    act on this specific resource). Both checks are required.
    """
    if str(current_driver.id) != str(driver_id):
        raise HTTPException(status_code=403, detail="Cannot act on behalf of another driver")


@router.post("/register", response_model=DriverOut)
def register_driver(driver_in: DriverCreate, db: Session = Depends(get_db)):
    """
    LEGACY endpoint from before auth existed — creates a driver with no
    password, unusable for login. Kept only so nothing that referenced it
    earlier in this project breaks. New drivers should use
    POST /auth/driver/signup instead, which sets a password and returns
    a usable token immediately.
    """
    existing = db.query(Driver).filter(Driver.phone_number == driver_in.phone_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Driver with this phone number already exists")

    driver = Driver(
        name=driver_in.name,
        phone_number=driver_in.phone_number,
        vehicle_number=driver_in.vehicle_number,
        vehicle_type=driver_in.vehicle_type,
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)
    return driver


@router.post("/{driver_id}/location")
async def report_location(
    driver_id: str,
    location: LocationUpdate,
    db: Session = Depends(get_db),
    current_driver: Driver = Depends(get_current_driver),
):
    """
    Called repeatedly (every 2-5 sec) by a driver's app to report their
    current position. Writes ONLY to Redis — never to Postgres.

    NOW REQUIRES AUTH: the caller must be logged in AS this exact driver.
    Without this, anyone could spoof any driver's location by just
    guessing/knowing their UUID — a real integrity problem, since
    matching decisions and fare/ETA all depend on this data being honest.
    """
    _require_self(driver_id, current_driver)

    # Location pings are expected every 2-5 sec normally -- this limit
    # (max 20 per 10 sec) catches a malfunctioning/malicious client
    # spamming far above realistic GPS frequency, without interfering
    # with normal usage.
    check_rate_limit(f"ratelimit:location:{driver_id}", max_requests=20, window_seconds=10)

    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    update_driver_location(driver_id, location.longitude, location.latitude)

    active_trip = find_active_trip_for_driver(db, driver_id)
    if active_trip:
        # Durable route log — every ping during an active trip, kept for
        # replay/history. Separate concern from the throttled WebSocket
        # push below: we NEVER throttle what we persist, only what we
        # push live, since a sparse route history would be a real loss
        # later (dispute resolution, analytics) even if frequent live
        # pushes aren't needed for the rider's screen.
        db.add(TripLocationLog(
            trip_id=active_trip.id,
            latitude=location.latitude,
            longitude=location.longitude,
        ))
        db.commit()

        if should_push_location(str(active_trip.id), location.latitude, location.longitude):
            await rider_manager.send_to(
                str(active_trip.rider_id),
                driver_location_update_event(active_trip.id, location.latitude, location.longitude),
            )

    return {"status": "location updated"}


@router.post("/{driver_id}/go-online", response_model=DriverOut)
def go_online(driver_id: str, db: Session = Depends(get_db), current_driver: Driver = Depends(get_current_driver)):
    """
    The real mechanism a driver's app calls when they tap 'Go Online'.
    NOW REQUIRES AUTH + ownership — a driver can only toggle their own
    availability, never another driver's.
    """
    _require_self(driver_id, current_driver)

    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    driver.is_available = True
    db.commit()
    db.refresh(driver)
    return driver


@router.post("/{driver_id}/go-offline", response_model=DriverOut)
def go_offline(driver_id: str, db: Session = Depends(get_db), current_driver: Driver = Depends(get_current_driver)):
    _require_self(driver_id, current_driver)

    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    driver.is_available = False
    db.commit()
    db.refresh(driver)
    return driver
