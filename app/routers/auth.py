from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.driver import Driver
from app.models.rider import Rider
from app.schemas.auth import DriverSignup, RiderSignup, LoginRequest, Token
from app.core.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/driver/signup", response_model=Token)
def driver_signup(payload: DriverSignup, db: Session = Depends(get_db)):
    existing = db.query(Driver).filter(Driver.phone_number == payload.phone_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    driver = Driver(
        name=payload.name,
        phone_number=payload.phone_number,
        vehicle_number=payload.vehicle_number,
        vehicle_type=payload.vehicle_type,
        hashed_password=hash_password(payload.password),
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)

    token = create_access_token(subject=str(driver.id), role="driver")
    return Token(access_token=token, role="driver")


@router.post("/driver/login", response_model=Token)
def driver_login(payload: LoginRequest, db: Session = Depends(get_db)):
    driver = db.query(Driver).filter(Driver.phone_number == payload.phone_number).first()
    # Deliberately identical error for "no such user" and "wrong password"
    # — revealing WHICH one failed lets an attacker enumerate valid phone
    # numbers by testing many and watching the error message change.
    if not driver or not driver.hashed_password or not verify_password(payload.password, driver.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid phone number or password")

    token = create_access_token(subject=str(driver.id), role="driver")
    return Token(access_token=token, role="driver")


@router.post("/rider/signup", response_model=Token)
def rider_signup(payload: RiderSignup, db: Session = Depends(get_db)):
    existing = db.query(Rider).filter(Rider.phone_number == payload.phone_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered")

    rider = Rider(
        name=payload.name,
        phone_number=payload.phone_number,
        hashed_password=hash_password(payload.password),
    )
    db.add(rider)
    db.commit()
    db.refresh(rider)

    token = create_access_token(subject=str(rider.id), role="rider")
    return Token(access_token=token, role="rider")


@router.post("/rider/login", response_model=Token)
def rider_login(payload: LoginRequest, db: Session = Depends(get_db)):
    rider = db.query(Rider).filter(Rider.phone_number == payload.phone_number).first()
    if not rider or not rider.hashed_password or not verify_password(payload.password, rider.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid phone number or password")

    token = create_access_token(subject=str(rider.id), role="rider")
    return Token(access_token=token, role="rider")
