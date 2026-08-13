"""baseline schema - drivers, riders, trips

Revision ID: 0001
Revises:
Create Date: 2026-08-12

This migration represents the schema as it exists RIGHT NOW after Phases
0-6, built by create_all() and manual table drops. Since Alembic wasn't
in place from the start, this baseline is written to match current
reality — it is NOT meant to be run against a fresh empty database only;
see the note in README/migration workflow about stamping vs upgrading
an existing database.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drivers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False, unique=True),
        sa.Column("vehicle_number", sa.String(), nullable=False, unique=True),
        sa.Column("vehicle_type", sa.String(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_drivers_id", "drivers", ["id"])
    op.create_index("ix_drivers_phone_number", "drivers", ["phone_number"])

    op.create_table(
        "riders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_riders_id", "riders", ["id"])
    op.create_index("ix_riders_phone_number", "riders", ["phone_number"])

    trip_status_enum = postgresql.ENUM(
        "requested", "ongoing", "completed", "cancelled", name="tripstatus"
    )
    trip_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "trips",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("riders.id"), nullable=False),
        sa.Column("driver_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("drivers.id"), nullable=False),
        sa.Column("pickup_latitude", sa.Float(), nullable=False),
        sa.Column("pickup_longitude", sa.Float(), nullable=False),
        sa.Column("estimated_fare", sa.Float(), nullable=True),
        sa.Column("eta_minutes", sa.Float(), nullable=True),
        sa.Column("status", trip_status_enum, nullable=False, server_default="requested"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trips_id", "trips", ["id"])


def downgrade() -> None:
    op.drop_table("trips")
    postgresql.ENUM(name="tripstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_riders_phone_number", table_name="riders")
    op.drop_index("ix_riders_id", table_name="riders")
    op.drop_table("riders")
    op.drop_index("ix_drivers_phone_number", table_name="drivers")
    op.drop_index("ix_drivers_id", table_name="drivers")
    op.drop_table("drivers")
