from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.driver import Driver
from app.schemas.driver import DriverCreate, DriverOut, LocationUpdate
from app.core.geo_utils import update_driver_location

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
def report_location(driver_id: str, location: LocationUpdate, db: Session = Depends(get_db)):
    """
    Called repeatedly (every 2-5 sec) by a driver's app to report their
    current position. Writes ONLY to Redis — never to Postgres.

    We still check Postgres to confirm the driver_id is a real, registered
    driver — a cheap lookup, not a write, so it doesn't carry the write-
    amplification cost we're avoiding.
    """
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    update_driver_location(driver_id, location.longitude, location.latitude)
    return {"status": "location updated"}
