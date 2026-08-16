"""add hashed_password to drivers and riders

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: safe to re-run if a prior deploy partially applied this migration
    op.execute("ALTER TABLE drivers ADD COLUMN IF NOT EXISTS hashed_password VARCHAR")
    op.execute("ALTER TABLE riders ADD COLUMN IF NOT EXISTS hashed_password VARCHAR")


def downgrade() -> None:
    op.execute("ALTER TABLE riders DROP COLUMN IF EXISTS hashed_password")
    op.execute("ALTER TABLE drivers DROP COLUMN IF EXISTS hashed_password")
