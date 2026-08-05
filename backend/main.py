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
