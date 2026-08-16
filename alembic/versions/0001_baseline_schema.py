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


def enum_exists(enum_name):
    """Check if an enum type exists in the current database."""
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM pg_type WHERE typname = :name)"
    ), {"name": enum_name})
    return result.scalar()


def upgrade() -> None:
    # Create enum only if it doesn't exist
    if not enum_exists("tripstatus"):
        trip_status_enum = postgresql.ENUM(
            "requested", "ongoing", "completed", "cancelled", name="tripstatus"
        )
        trip_status_enum.create(op.get_bind(), checkfirst=False)

    # These CREATE TABLE IF NOT EXISTS statements handle existing tables gracefully
    op.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            id UUID PRIMARY KEY,
            name VARCHAR NOT NULL,
            phone_number VARCHAR NOT NULL UNIQUE,
            vehicle_number VARCHAR NOT NULL UNIQUE,
            vehicle_type VARCHAR NOT NULL,
            is_available BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE,
            hashed_password VARCHAR
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_drivers_id ON drivers (id);
        CREATE INDEX IF NOT EXISTS ix_drivers_phone_number ON drivers (phone_number);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS riders (
            id UUID PRIMARY KEY,
            name VARCHAR NOT NULL,
            phone_number VARCHAR NOT NULL UNIQUE,
            created_at TIMESTAMP WITH TIME ZONE,
            hashed_password VARCHAR
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_riders_id ON riders (id);
        CREATE INDEX IF NOT EXISTS ix_riders_phone_number ON riders (phone_number);
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id UUID PRIMARY KEY,
            rider_id UUID NOT NULL REFERENCES riders(id),
            driver_id UUID NOT NULL REFERENCES drivers(id),
            pickup_latitude FLOAT NOT NULL,
            pickup_longitude FLOAT NOT NULL,
            estimated_fare FLOAT,
            eta_minutes FLOAT,
            status tripstatus NOT NULL DEFAULT 'requested',
            created_at TIMESTAMP WITH TIME ZONE
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_trips_id ON trips (id);
    """)


def downgrade() -> None:
    op.drop_table("trips")
    postgresql.ENUM(name="tripstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_riders_phone_number", table_name="riders")
    op.drop_index("ix_riders_id", table_name="riders")
    op.drop_table("riders")
    op.drop_index("ix_drivers_phone_number", table_name="drivers")
    op.drop_index("ix_drivers_id", table_name="drivers")
    op.drop_table("drivers")

