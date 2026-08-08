"""add_trade_close_fields

Revision ID: a9f3c1e2d4b5
Revises: e4b12c5bf3ef
Create Date: 2026-08-08 00:00:00.000000

Adds close_price and close_reason to the trades table (Section 9 — Trade Manager).
Uses ADD COLUMN IF NOT EXISTS so the migration is idempotent on existing DBs.
"""
from alembic import op


revision: str = "a9f3c1e2d4b5"
down_revision = "e4b12c5bf3ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS close_price FLOAT")
    op.execute("ALTER TABLE trades ADD COLUMN IF NOT EXISTS close_reason VARCHAR(100)")


def downgrade() -> None:
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS close_price")
    op.execute("ALTER TABLE trades DROP COLUMN IF EXISTS close_reason")
