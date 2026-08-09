"""add unique partial index for open trades (duplicate protection)

Revision ID: d5e6f7a8b9c0
Revises: c2d3e4f5a6b7
Create Date: 2026-08-09

Task 6 — Race-condition duplicate trade protection.

Adds a PostgreSQL partial unique index on (pair, direction) WHERE status='open'.
This enforces at the database level that only ONE open position per pair/direction
can exist at any time, eliminating the read-before-write race condition in the
ConcreteTradeManager duplicate check.

The application-layer check in ConcreteTradeManager.open_trade() remains as a
fast first-pass guard; the DB index is the definitive enforcement gate.

On violation the DB raises IntegrityError (psycopg2 / asyncpg unique violation),
which is caught by ConcreteTradeManager and returned as OrderResult(success=False).
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Partial unique index: only one open trade per pair+direction allowed.
    # Closed, cancelled, and pending trades are excluded from the constraint.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_open_pair_direction
        ON trades (pair, direction)
        WHERE status = 'open'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_trades_open_pair_direction")
