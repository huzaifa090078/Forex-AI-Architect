"""
AI Forex Trading Bot — FastAPI Application Entry Point
"""

import logging
import os

import sqlalchemy as sa
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import engine, Base, AsyncSessionLocal
from app.modules.market_scanner.live_feed import market_data_feed
from app.modules.market_scanner.scanner import market_scanner as _market_scanner
from app.modules.trade_manager.monitor import trade_monitor
from app.modules.news_filter.monitor import news_monitor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Forex Trading Bot",
        description=(
            "Production-grade REST API for an AI-driven Forex trading platform. "
            "Covers authentication, live trade management, AI signal generation, "
            "market scanning, backtesting, news filtering, and bot configuration."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url="/api/redoc",
    )

    # ── CORS ────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ─────────────────────────────────────────────────────────────
    app.include_router(api_router, prefix="/api")

    # ── Lifecycle ───────────────────────────────────────────────────────────
    async def _on_candle(pair: str, timeframe: str, bar: dict) -> None:
        """
        Candle event callback — automatically triggered by MarketDataFeed
        whenever a new completed candle is detected for any pair/timeframe.

        Re-scans the affected pair across all timeframes so the best
        opportunity is always up-to-date without polling.
        """
        try:
            result = await _market_scanner.scan_pair(pair)
            if result is not None:
                logger.info(
                    "Candle scan [%s/%s]: %s → %s score=%.2f priority=%s session=%s",
                    pair, timeframe,
                    result.pair, result.direction,
                    result.score, result.priority_level, result.session,
                )
        except Exception as exc:
            logger.error(
                "Candle-triggered scan failed for %s/%s: %s", pair, timeframe, exc
            )

    @app.on_event("startup")
    async def on_startup() -> None:
        # ── Schema bootstrap (dev convenience; use Alembic in production) ──
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Section 9: idempotently add close_price / close_reason columns
            # to existing DBs that pre-date the migration.
            await conn.execute(
                sa.text(
                    "ALTER TABLE trades "
                    "ADD COLUMN IF NOT EXISTS close_price FLOAT"
                )
            )
            await conn.execute(
                sa.text(
                    "ALTER TABLE trades "
                    "ADD COLUMN IF NOT EXISTS close_reason VARCHAR(100)"
                )
            )
            # Section 10: idempotently create news_events table + indexes
            await conn.execute(sa.text("""
                CREATE TABLE IF NOT EXISTS news_events (
                    id         VARCHAR PRIMARY KEY,
                    provider   VARCHAR(50)  NOT NULL DEFAULT 'unavailable',
                    event_name VARCHAR(255) NOT NULL,
                    currency   VARCHAR(10)  NOT NULL,
                    impact     VARCHAR(20)  NOT NULL,
                    event_time TIMESTAMPTZ  NOT NULL,
                    source     VARCHAR(100),
                    actual     VARCHAR(50),
                    forecast   VARCHAR(50),
                    previous   VARCHAR(50),
                    status     VARCHAR(20)  NOT NULL DEFAULT 'upcoming',
                    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                )
            """))
            await conn.execute(sa.text("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_news_event_identity
                ON news_events (provider, event_name, currency, event_time)
            """))
            await conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_news_events_currency   ON news_events (currency)"))
            await conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_news_events_impact     ON news_events (impact)"))
            await conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_news_events_event_time ON news_events (event_time)"))
            await conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_news_events_status     ON news_events (status)"))

        # ── Ensure system bot user exists ────────────────────────────────────
        from app.modules.trade_manager.service import TradeService
        try:
            async with AsyncSessionLocal() as db:
                await TradeService.ensure_bot_user(db)
        except Exception as exc:
            logger.warning("Startup: could not create bot user: %s", exc)

        # ── Live market-data feed (Section 3) ────────────────────────────────
        # Connects to MT5/Exness on first data request; raises RuntimeError on
        # non-Windows which the feed catches and logs as a warning.
        await market_data_feed.start()

        # Wire the scanner to the candle feed — every completed candle
        # automatically triggers a fresh scan for the affected pair.
        market_data_feed.subscribe_candles(_on_candle)

        # ── News Filter monitoring (Section 10) ─────────────────────────────
        await news_monitor.start()

        # ── Trade position monitoring (Section 9) ────────────────────────────
        await trade_monitor.start()

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        # Stop monitors before the event loop closes.
        await trade_monitor.stop()
        await news_monitor.stop()
        # Stop the live feed and dispose of the DB engine.
        await market_data_feed.stop()
        await engine.dispose()

    return app


app = create_app()

# ---------------------------------------------------------------------------
# Dev server entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Replit injects PORT; fall back to APP_PORT from settings for local dev.
    port = int(os.environ.get("PORT", settings.APP_PORT))
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=port,
        reload=settings.APP_DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
