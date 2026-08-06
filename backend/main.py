"""
AI Forex Trading Bot — FastAPI Application Entry Point
"""

import os

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import engine, Base
from app.modules.market_scanner.live_feed import market_data_feed
from app.modules.market_scanner.scanner import market_scanner as _market_scanner

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
        # Create all tables (dev convenience — use Alembic in production)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Start the Section 3 live market-data feed (tick polling + candle
        # detection).  The feed connects to MT5/Exness on first data request;
        # on non-Windows platforms the connector raises RuntimeError which the
        # feed catches and logs as a warning, so startup is never blocked.
        await market_data_feed.start()

        # Wire the scanner to the candle feed — every completed candle
        # automatically triggers a fresh scan for the affected pair.
        # Uses the existing subscribe_candles() infrastructure; no polling loop.
        market_data_feed.subscribe_candles(_on_candle)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        # Stop the live feed before the event loop closes so background tasks
        # can finish cleanly without CancelledError noise in the logs.
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
