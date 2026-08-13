"""add trip_location_logs table for route history

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_location_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id"), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trip_location_logs_id", "trip_location_logs", ["id"])
    op.create_index("ix_trip_location_logs_trip_id", "trip_location_logs", ["trip_id"])


def downgrade() -> None:
    op.drop_index("ix_trip_location_logs_trip_id", table_name="trip_location_logs")
    op.drop_index("ix_trip_location_logs_id", table_name="trip_location_logs")
    op.drop_table("trip_location_logs")
