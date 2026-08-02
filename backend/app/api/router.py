"""
Top-level API router.
Aggregates all versioned sub-routers and the health endpoint.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.trades import router as trades_router
from app.api.v1.signals import router as signals_router
from app.api.v1.market import router as market_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.news import router as news_router
from app.api.v1.settings import router as settings_router
from app.api.v1.logs import router as logs_router

api_router = APIRouter()


# ── Health (unversioned) ─────────────────────────────────────────────────────
@api_router.get("/healthz", tags=["health"])
async def healthz() -> dict:
    return {"status": "ok"}


# ── v1 routes ────────────────────────────────────────────────────────────────
api_router.include_router(auth_router,       prefix="/v1/auth",       tags=["auth"])
api_router.include_router(dashboard_router,  prefix="/v1/dashboard",  tags=["dashboard"])
api_router.include_router(trades_router,     prefix="/v1/trades",     tags=["trades"])
api_router.include_router(signals_router,    prefix="/v1/signals",    tags=["signals"])
api_router.include_router(market_router,     prefix="/v1/market",     tags=["market"])
api_router.include_router(backtests_router,  prefix="/v1/backtests",  tags=["backtests"])
api_router.include_router(news_router,       prefix="/v1/news",       tags=["news"])
api_router.include_router(settings_router,   prefix="/v1/settings",   tags=["settings"])
api_router.include_router(logs_router,       prefix="/v1/logs",       tags=["logs"])
