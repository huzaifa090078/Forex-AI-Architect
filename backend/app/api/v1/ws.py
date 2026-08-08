"""
WebSocket endpoint — Section 11 real-time data bridge.

Architecture:
  MT5 → Backend services → WebSocket → Dashboard

Single shared connection per client.  Server pushes:
  • tick         — live price updates for all 10 pairs
  • status       — bot/MT5/news filter status
  • notification — trade events, news alerts, system events

Client can send:
  • {"type": "ping"}             → server replies {"type": "pong"}
  • {"type": "subscribe_pair", "pair": "EURUSD"}   → ignored (all pairs are always streamed)

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

# Tick interval for pushing prices (seconds)
_TICK_INTERVAL   = 3.0
_STATUS_INTERVAL = 10.0


def _make_tick_frame(pair: str) -> Optional[Dict[str, Any]]:
    """Build a tick frame from live_feed cache. Returns None if no data."""
    tick = market_data_feed.get_last_tick(pair)
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
    from app.modules.market_scanner.live_feed import market_data_feed

    task = getattr(news_monitor, "_task", None)
    if task is None:
        bot_status = "stopped"
    elif task.done():
        bot_status = "error" if not task.cancelled() and task.exception() else "stopped"
    else:
        bot_status = "running"

    return {
        "type":              "status",
        "bot_status":        bot_status,
        "news_filter_ok":    news_filter.provider_available,
        "mt5_available":     False,          # Linux/Replit: always false; Windows backend fills this
        "last_refresh":      news_filter.last_refresh.isoformat() if news_filter.last_refresh else None,
        "time":              datetime.now(timezone.utc).isoformat(),
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

            # ── push status ──
            if now - last_status_push >= _STATUS_INTERVAL:
                try:
                    await ws.send_json(_make_status_frame())
                    last_status_push = now
                except Exception:
                    break

            # ── push ticks ──
            if now - last_tick_push >= _TICK_INTERVAL:
                for pair in FOREX_PAIRS:
                    frame = _make_tick_frame(pair)
                    if frame:
                        try:
                            await ws.send_json(frame)
                        except Exception:
                            break
                last_tick_push = now

            # ── non-blocking receive (handle ping/pong) ──
            try:
                msg_text = await asyncio.wait_for(ws.receive_text(), timeout=0.05)
                try:
                    msg = json.loads(msg_text)
                    if msg.get("type") == "ping":
                        await ws.send_json({"type": "pong", "time": datetime.now(timezone.utc).isoformat()})
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
