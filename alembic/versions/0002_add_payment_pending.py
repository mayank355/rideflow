"""add payment_pending trip status

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-13
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres requires adding enum values outside a transaction block in
    # older versions; ALTER TYPE ... ADD VALUE is transactional-safe in
    # PG12+, which is what we're running (16), so this is safe as-is.
    op.execute("ALTER TYPE tripstatus ADD VALUE IF NOT EXISTS 'payment_pending'")


def downgrade() -> None:
    # Postgres does not support removing a single enum value directly.
    # A real downgrade would require creating a new enum type without
    # the value, migrating the column over, then dropping the old type —
    # non-trivial and risky if any row currently uses 'payment_pending'.
    # Left as a no-op; documented rather than silently incorrect.
    pass
