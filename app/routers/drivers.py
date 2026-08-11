from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.driver import Driver
from app.schemas.driver import DriverCreate, DriverOut, LocationUpdate
from app.core.geo_utils import update_driver_location
from app.routers.trips import find_active_trip_for_driver
from app.websocket.manager import rider_manager
from app.websocket.events import driver_location_update_event

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.post("/register", response_model=DriverOut)
def register_driver(driver_in: DriverCreate, db: Session = Depends(get_db)):
    """
    Writes a new driver into Postgres — the durable 'register book' entry.
    This does NOT touch Redis at all; location is reported separately,
    only once the driver actually goes online.
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
async def report_location(driver_id: str, location: LocationUpdate, db: Session = Depends(get_db)):
    """
    Called repeatedly (every 2-5 sec) by a driver's app to report their
    current position. Writes ONLY to Redis — never to Postgres.

    We still check Postgres to confirm the driver_id is a real, registered
    driver — a cheap lookup, not a write, so it doesn't carry the write-
    amplification cost we're avoiding.

    NEW in Phase 6: if this driver currently has an ONGOING trip, also
    push their location live to that trip's rider — this is the actual
    "moving car icon on a map" mechanism. Every other part of this
    function is unchanged from Phase 1; this is purely additive.
    """
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    update_driver_location(driver_id, location.longitude, location.latitude)

    active_trip = find_active_trip_for_driver(db, driver_id)
    if active_trip:
        await rider_manager.send_to(
            str(active_trip.rider_id),
            driver_location_update_event(active_trip.id, location.latitude, location.longitude),
        )

    return {"status": "location updated"}


@router.post("/{driver_id}/go-online", response_model=DriverOut)
def go_online(driver_id: str, db: Session = Depends(get_db)):
    """
    The real mechanism a driver's app calls when they tap 'Go Online'.
    This is the actual replacement for every manual psql UPDATE we ran
    during testing — same effect, triggered by a real request instead of
    hand-typed SQL.

    NOTE: this only flips availability in Postgres. It deliberately does
    NOT touch Redis — a driver could go online here but never report a
    location, in which case GEOSEARCH simply won't find them (correct
    behavior: no location means no way to know they're nearby, regardless
    of their availability flag).
    """
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    driver.is_available = True
    db.commit()
    db.refresh(driver)
    return driver


@router.post("/{driver_id}/go-offline", response_model=DriverOut)
def go_offline(driver_id: str, db: Session = Depends(get_db)):
    """
    The counterpart to go-online. Note this does NOT delete the driver's
    Redis location — their last known position simply stays there,
    unused, until it's naturally overwritten by their next location
    report whenever they reconnect. GEOSEARCH would still technically
    find them geographically, but the is_available=False check in
    find_best_available_driver correctly filters them out regardless.
    """
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    driver.is_available = False
    db.commit()
    db.refresh(driver)
    return driver
