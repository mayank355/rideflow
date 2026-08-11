import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class TripStatus(str, enum.Enum):
    REQUESTED = "requested"   # driver matched, not yet picked up
    ONGOING = "ongoing"       # picked up, trip in progress (Phase 3+)
    COMPLETED = "completed"   # trip finished (Phase 3+)
    CANCELLED = "cancelled"


class Trip(Base):
    __tablename__ = "trips"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Foreign keys — this is the relational integrity Postgres gives us
    # that Redis never could: a trip MUST reference a real rider and driver.
    rider_id = Column(UUID(as_uuid=True), ForeignKey("riders.id"), nullable=False)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("drivers.id"), nullable=False)

    pickup_latitude = Column(Float, nullable=False)
    pickup_longitude = Column(Float, nullable=False)

    estimated_fare = Column(Float, nullable=True)
    eta_minutes = Column(Float, nullable=True)

    status = Column(Enum(TripStatus), default=TripStatus.REQUESTED, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
