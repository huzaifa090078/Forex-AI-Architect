"""
WebSocket endpoint — Section 11 real-time data bridge.

Architecture:
  MT5 → Backend services → WebSocket → Dashboard

Single shared connection per client.  Server pushes:
  • tick         — live price updates for all 10 pairs
  • status       — bot/MT5/news filter status
  • notification — trade events, news alerts, system events

Client can send:
  • {"type": "ping"}  → server replies {"type": "pong"}

Security: no credentials are ever sent through WebSocket frames.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.modules.market_scanner.live_feed import market_data_feed
from app.modules.news_filter.monitor import news_filter
from app.modules.market_scanner.scanner import FOREX_PAIRS

logger = logging.getLogger(__name__)
router = APIRouter()

# ── In-memory tick cache (pair → last tick dict) ──────────────────────────────
_tick_cache: Dict[str, Dict[str, Any]] = {}


async def _on_tick(pair: str, tick: dict) -> None:
    """Subscriber callback — stores latest tick per pair."""
    _tick_cache[pair] = tick


def _register_ws_subscriber() -> None:
    """Subscribe to live feed once at startup."""
    market_data_feed.subscribe_ticks(_on_tick)


# Called from main.py startup
register_ws_subscriber = _register_ws_subscriber

# Tick interval for pushing prices (seconds)
_TICK_INTERVAL   = 3.0
_STATUS_INTERVAL = 10.0


def _make_tick_frame(pair: str) -> Optional[Dict[str, Any]]:
    """Build a tick frame from the in-memory cache. Returns None if no data yet."""
    tick = _tick_cache.get(pair)
    if tick is None:
        return None
    return {
        "type":   "tick",
        "pair":   pair,
        "bid":    tick.get("bid"),
        "ask":    tick.get("ask"),
        "spread": round(tick.get("spread", 0), 5),
        "time":   datetime.now(timezone.utc).isoformat(),
    }


def _make_status_frame() -> Dict[str, Any]:
    """Build a status frame — never includes credentials."""
    from app.modules.news_filter.monitor import news_monitor

    task = getattr(news_monitor, "_task", None)
    if task is None:
        bot_status = "stopped"
    elif task.done():
        bot_status = "error" if not task.cancelled() and task.exception() else "stopped"
    else:
        bot_status = "running"

    return {
        "type":           "status",
        "bot_status":     bot_status,
        "news_filter_ok": news_filter.provider_available,
        "mt5_available":  False,   # Linux/Replit: always false
        "last_refresh":   news_filter.last_refresh.isoformat() if news_filter.last_refresh else None,
        "time":           datetime.now(timezone.utc).isoformat(),
    }


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    logger.info("ws: client connected %s", ws.client)

    last_tick_push   = 0.0
    last_status_push = 0.0

    try:
        while True:
            now = asyncio.get_event_loop().time()

            # ── push status ──────────────────────────────────────────────────
            if now - last_status_push >= _STATUS_INTERVAL:
                try:
                    await ws.send_json(_make_status_frame())
                    last_status_push = now
                except Exception:
                    break

            # ── push ticks ───────────────────────────────────────────────────
            if now - last_tick_push >= _TICK_INTERVAL:
                for pair in FOREX_PAIRS:
                    frame = _make_tick_frame(pair)
                    if frame:
                        try:
                            await ws.send_json(frame)
                        except Exception:
                            break
                last_tick_push = now

            # ── non-blocking receive (ping/pong) ─────────────────────────────
            try:
                msg_text = await asyncio.wait_for(ws.receive_text(), timeout=0.05)
                try:
                    msg = json.loads(msg_text)
                    if msg.get("type") == "ping":
                        await ws.send_json({
                            "type": "pong",
                            "time": datetime.now(timezone.utc).isoformat(),
                        })
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.info("ws: client disconnected %s", ws.client)
    except Exception as exc:
        logger.warning("ws: error — %s", exc)
    finally:
        try:
            await ws.close()
        except Exception:
            pass
