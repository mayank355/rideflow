import uuid
from datetime import datetime
from pydantic import BaseModel


class RiderCreate(BaseModel):
    name: str
    phone_number: str


class RiderOut(BaseModel):
    id: uuid.UUID
    name: str
    phone_number: str
    created_at: datetime

    class Config:
        from_attributes = True
