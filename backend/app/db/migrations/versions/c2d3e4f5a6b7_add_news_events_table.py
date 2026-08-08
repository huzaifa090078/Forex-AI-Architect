"""add news_events table

Revision ID: c2d3e4f5a6b7
Revises: a9f3c1e2d4b5
Create Date: 2026-08-08 00:00:00.000000

Section 10 — News Filter Engine.
Adds news_events table with a unique identity constraint to prevent
duplicate records from repeated provider refreshes.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c2d3e4f5a6b7"
down_revision = "a9f3c1e2d4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_events",
        sa.Column("id",         sa.String(),                                   nullable=False),
        sa.Column("provider",   sa.String(50),  nullable=False, server_default="unavailable"),
        sa.Column("event_name", sa.String(255), nullable=False),
        sa.Column("currency",   sa.String(10),  nullable=False),
        sa.Column("impact",     sa.String(20),  nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source",     sa.String(100), nullable=True),
        sa.Column("actual",     sa.String(50),  nullable=True),
        sa.Column("forecast",   sa.String(50),  nullable=True),
        sa.Column("previous",   sa.String(50),  nullable=True),
        sa.Column("status",     sa.String(20),  nullable=False, server_default="upcoming"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "event_name", "currency", "event_time",
            name="uq_news_event_identity",
        ),
    )
    op.create_index("ix_news_events_currency",   "news_events", ["currency"])
    op.create_index("ix_news_events_impact",     "news_events", ["impact"])
    op.create_index("ix_news_events_event_time", "news_events", ["event_time"])
    op.create_index("ix_news_events_status",     "news_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_news_events_status",     table_name="news_events")
    op.drop_index("ix_news_events_event_time", table_name="news_events")
    op.drop_index("ix_news_events_impact",     table_name="news_events")
    op.drop_index("ix_news_events_currency",   table_name="news_events")
    op.drop_table("news_events")
