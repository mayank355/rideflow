import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class DriverCreate(BaseModel):
    name: str
    phone_number: str
    vehicle_number: str
    vehicle_type: str


class DriverOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_number: str
    vehicle_number: str
    vehicle_type: str
    is_available: bool
    created_at: datetime

    class Config:
        from_attributes = True  # allows creating this from a SQLAlchemy model instance


class LocationUpdate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
