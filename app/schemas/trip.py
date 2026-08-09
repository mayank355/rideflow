import uuid
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.trip import TripStatus


class RideRequest(BaseModel):
    rider_id: uuid.UUID
    pickup_latitude: float = Field(..., ge=-90, le=90)
    pickup_longitude: float = Field(..., ge=-180, le=180)


class TripOut(BaseModel):
    id: uuid.UUID
    rider_id: uuid.UUID
    driver_id: uuid.UUID
    pickup_latitude: float
    pickup_longitude: float
    status: TripStatus
    created_at: datetime

    class Config:
        from_attributes = True
