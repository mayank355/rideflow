from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.rider import Rider
from app.schemas.rider import RiderCreate, RiderOut

router = APIRouter(prefix="/riders", tags=["riders"])


@router.post("/register", response_model=RiderOut)
def register_rider(rider_in: RiderCreate, db: Session = Depends(get_db)):
    existing = db.query(Rider).filter(Rider.phone_number == rider_in.phone_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Rider with this phone number already exists")

    rider = Rider(name=rider_in.name, phone_number=rider_in.phone_number)
    db.add(rider)
    db.commit()
    db.refresh(rider)
    return rider
