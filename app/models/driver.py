import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class Driver(Base):
    __tablename__ = "drivers"

    # UUID primary key — globally unique, no shard-collision risk at scale
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Identity fields — written once, rarely change
    name = Column(String, nullable=False)
    phone_number = Column(String, unique=True, nullable=False, index=True)
    vehicle_number = Column(String, unique=True, nullable=False)
    vehicle_type = Column(String, nullable=False)  # e.g. "sedan", "bike", "auto"

    # Status — changes occasionally (online/offline toggle), NOT every few seconds
    is_available = Column(Boolean, default=False, nullable=False)

    # Metadata
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # NOTE: current lat/lng is intentionally NOT a column here.
    # Live location lives ONLY in Redis (GEOADD) — see app/core/geo_utils.py
    # Reason: location changes every few seconds; storing it here would mean
    # constant UPDATE writes on a disk-backed table with indexes, i.e. the
    # write-amplification problem we walked through in Phase 0.
