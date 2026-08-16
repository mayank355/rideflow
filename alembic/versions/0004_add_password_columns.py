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
    op.add_column("drivers", sa.Column("hashed_password", sa.String(), nullable=True))
    op.add_column("riders", sa.Column("hashed_password", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("riders", "hashed_password")
    op.drop_column("drivers", "hashed_password")
