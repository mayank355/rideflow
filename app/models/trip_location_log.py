import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class TripLocationLog(Base):
    """
    One row per location ping received DURING an active trip. This is
    intentionally separate from the live Redis location (Phase 1) —
    Redis holds only the CURRENT position, ephemeral by design. This
    table holds the full HISTORY of a trip's route, durable, for later
    playback/replay — a genuinely different access pattern (write-once-
    per-ping, read-rarely-in-bulk-afterward) than the hot-path Redis data.

    Why Postgres and not Redis for this: this data has long-term value
    (a completed trip's route might be needed for a dispute, an analytics
    pipeline, or a "view your route" feature days later) — the opposite
    of location's self-healing, throwaway nature while a trip is live.
    """
    __tablename__ = "trip_location_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id"), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
