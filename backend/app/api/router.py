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
from app.api.v1.smc import router as smc_router
from app.api.v1.ai import router as ai_router
from app.api.v1.risk import router as risk_router
from app.api.v1.candles import router as candles_router
from app.api.v1.mt5 import router as mt5_router
from app.api.v1.ws import router as ws_router

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
api_router.include_router(smc_router,        prefix="/v1/smc",        tags=["smc"])
api_router.include_router(ai_router,         prefix="/v1/ai",         tags=["ai"])
api_router.include_router(risk_router,       prefix="/v1/risk",       tags=["risk"])
api_router.include_router(candles_router,    prefix="/v1/candles",    tags=["candles"])
api_router.include_router(mt5_router,        prefix="/v1/mt5",        tags=["mt5"])

# ── WebSocket (root — no /api prefix to avoid proxy rewriting) ───────────────
api_router.include_router(ws_router, tags=["ws"])
