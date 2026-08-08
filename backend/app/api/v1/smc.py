"""
SMC (Smart Money Concepts) routes — structural analysis and confluence scoring.

GET /v1/smc/structures   — detected SMC structures for a pair/timeframe
GET /v1/smc/confluence   — normalized 0–100 SMC confluence score for a pair

Both endpoints are read-only structural-analysis surfaces.  They run the same
SMC engine used by the Market Scanner but expose results independently so the
Dashboard can display SMC data without triggering a full scanner run.

Authentication:  consistent with the existing market-data routes — no JWT
                 dependency (read-only, non-sensitive market-structure data).

Error conventions (matching market.py):
  422 — invalid pair or timeframe query parameter
  503 — market data or SMC analysis unavailable for the requested pair
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db.schemas import ConfluenceFactorOut, ConfluenceResultOut, SMCStructureOut
from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.scanner import FOREX_PAIRS
from app.modules.smc import SMCAnalyzer
from app.modules.smc.interfaces import SMCStructure

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Module-level singletons ───────────────────────────────────────────────────

_data_service = MarketDataService()
_smc          = SMCAnalyzer()       # stateless; safe to reuse across requests

# Canonical SMC timeframe list (H4 → H1 → M15 → M5 priority, stored low→high).
# Stored M5-first so enumerate() gives priority weights matching the engine.
_SMC_TFS: List[str] = ["M5", "M15", "H1", "H4"]

# Display order for structures (H4 most significant → M5 entry context).
_TF_PRIORITY: Dict[str, int] = {tf: i for i, tf in enumerate(reversed(_SMC_TFS))}
# → H4=0, H1=1, M15=2, M5=3  (lower = higher priority = sorted first)

_OHLCV_COUNT = 60   # bars per timeframe — same budget as the Market Scanner

_VALID_PAIRS      = set(FOREX_PAIRS)
_VALID_TIMEFRAMES = set(_SMC_TFS)


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _struct_to_out(s: SMCStructure, pair: str) -> SMCStructureOut:
    """
    Convert an internal SMCStructure dataclass to its API response schema.

    ``pair`` is passed explicitly because the SMC engine always leaves
    SMCStructure.pair as "" (the _PAIR_UNSET sentinel); enrichment happens
    at the API boundary, never inside the engine.
    """
    # Zone is a str-Enum so .value is safe; guard for any future bare strings.
    zone_str = s.zone.value if hasattr(s.zone, "value") else str(s.zone)
    return SMCStructureOut(
        pattern=s.pattern.value,
        pair=pair,
        timeframe=s.timeframe,
        zone=zone_str,
        price_low=round(s.price_low, 5),
        price_high=round(s.price_high, 5),
        direction=s.direction,
        strength=round(s.strength, 4),
        validated=s.validated,
        detected_at=s.detected_at,
        metadata=s.metadata,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/structures", response_model=List[SMCStructureOut])
async def get_smc_structures(
    pair: str = Query(
        ...,
        description=(
            "Forex pair to analyse. "
            f"Allowed values: {', '.join(sorted(FOREX_PAIRS))}."
        ),
    ),
    timeframe: Optional[str] = Query(
        default=None,
        description=(
            "Restrict results to a single timeframe. "
            f"Allowed values: {', '.join(_SMC_TFS)}. "
            "Omit to return structures from all four SMC timeframes."
        ),
    ),
) -> List[SMCStructureOut]:
    """
    Detect and return SMC structures for the requested pair.

    Five structure categories are returned (when present):

    - **Market Structure** — Break of Structure (BOS) and Change of Character (CHoCH) events.
    - **Order Blocks** — unmitigated Order Blocks and Breaker Blocks.
    - **Fair Value Gaps** — Fair Value Gaps and price imbalances.
    - **Liquidity** — equal highs/lows, swing points, and stop-hunt levels.
    - **Supply/Demand Zones** — consolidation-base Supply/Demand zones and Mitigation Blocks.

    Results are ordered H4 → H1 → M15 → M5, then by ``strength`` descending
    within each timeframe.  The ``pair`` field on every item is always set to
    the requested pair (the SMC engine uses an empty sentinel internally).
    """
    pair = pair.upper()

    if pair not in _VALID_PAIRS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid pair '{pair}'. "
                f"Must be one of: {', '.join(sorted(FOREX_PAIRS))}"
            ),
        )
    if timeframe is not None and timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid timeframe '{timeframe}'. "
                f"Must be one of: {', '.join(_SMC_TFS)}"
            ),
        )

    tfs = [timeframe] if timeframe else _SMC_TFS

    # Fetch OHLCV for all requested timeframes concurrently.
    raw_fetches = await asyncio.gather(
        *[_data_service.get_ohlcv(pair, tf, _OHLCV_COUNT) for tf in tfs],
        return_exceptions=True,
    )

    ohlcv_map: Dict[str, List[Dict[str, Any]]] = {}
    for tf, result in zip(tfs, raw_fetches):
        if isinstance(result, Exception):
            logger.debug(
                "smc.structures: %s/%s OHLCV fetch failed — %s", pair, tf, result
            )
        else:
            ohlcv_map[tf] = result

    if not ohlcv_map:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Market data unavailable for {pair} — "
                "all timeframe fetches failed."
            ),
        )

    try:
        mtf = _smc.analyze_multi_timeframe(ohlcv_map)
    except Exception as exc:
        logger.error(
            "smc.structures: analyze_multi_timeframe failed for %s — %s", pair, exc
        )
        raise HTTPException(
            status_code=503,
            detail="SMC structure analysis failed — see server logs.",
        )

    # Flatten all five structure categories from each available timeframe.
    flat: List[SMCStructure] = []
    for tf in tfs:                          # preserve requested order for grouping
        tfa = mtf.timeframes.get(tf)
        if tfa is None:
            continue
        for s in (
            tfa.structures
            + tfa.order_blocks
            + tfa.fvgs
            + tfa.liquidity
            + tfa.supply_demand
        ):
            flat.append(s)

    # Sort: H4 first (priority 0) → M5 last (priority 3); strength desc within TF.
    flat.sort(key=lambda s: (_TF_PRIORITY.get(s.timeframe, 99), -s.strength))

    return [_struct_to_out(s, pair) for s in flat]


@router.get("/confluence", response_model=ConfluenceResultOut)
async def get_smc_confluence(
    pair: str = Query(
        ...,
        description=(
            "Forex pair to score. "
            f"Allowed values: {', '.join(sorted(FOREX_PAIRS))}."
        ),
    ),
) -> ConfluenceResultOut:
    """
    Compute and return the normalized 0–100 SMC confluence score for a pair.

    Eight independent factors are evaluated (max points each):

    1. BOS/CHoCH multi-timeframe alignment (20 pts)
    2. Order Block at current price (15 pts)
    3. Fair Value Gap at current price (15 pts)
    4. Liquidity Sweep confirmation (15 pts)
    5. Supply/Demand zone alignment (15 pts)
    6. Premium/Discount zone alignment (10 pts)
    7. RSI-14 confirmation (5 pts)
    8. EMA-20 confirmation (5 pts)

    Factor max scores sum to 100.  ``confirmed_count`` reports how many
    factors fired in the expected direction (``score > 0``).

    Current price is taken from the live MT5 tick (bid/ask mid).  When the
    tick is unavailable (non-Windows dev environment), the last M5 close is
    used as a fallback so the endpoint remains functional during development.
    """
    pair = pair.upper()

    if pair not in _VALID_PAIRS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid pair '{pair}'. "
                f"Must be one of: {', '.join(sorted(FOREX_PAIRS))}"
            ),
        )

    # Fetch live tick + all SMC timeframe OHLCV concurrently.
    all_fetches = await asyncio.gather(
        _data_service.get_tick(pair),
        *[_data_service.get_ohlcv(pair, tf, _OHLCV_COUNT) for tf in _SMC_TFS],
        return_exceptions=True,
    )
    tick_result   = all_fetches[0]
    ohlcv_results = all_fetches[1:]

    # Build OHLCV map — silently skip failed timeframes.
    ohlcv_map: Dict[str, List[Dict[str, Any]]] = {}
    for tf, result in zip(_SMC_TFS, ohlcv_results):
        if isinstance(result, Exception):
            logger.debug(
                "smc.confluence: %s/%s OHLCV fetch failed — %s", pair, tf, result
            )
        else:
            ohlcv_map[tf] = result

    if not ohlcv_map:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Market data unavailable for {pair} — "
                "all timeframe fetches failed."
            ),
        )

    # Derive current price — prefer live tick mid; fall back to last OHLCV close.
    if isinstance(tick_result, Exception):
        logger.debug(
            "smc.confluence: tick fetch failed for %s — falling back to last close. %s",
            pair, tick_result,
        )
        fallback_bars = (
            ohlcv_map.get("M5")
            or ohlcv_map.get("M15")
            or next(iter(ohlcv_map.values()))
        )
        current_price = float(fallback_bars[-1]["close"])
    else:
        current_price = (float(tick_result["bid"]) + float(tick_result["ask"])) / 2.0

    try:
        mtf = _smc.analyze_multi_timeframe(ohlcv_map)
    except Exception as exc:
        logger.error(
            "smc.confluence: analyze_multi_timeframe failed for %s — %s", pair, exc
        )
        raise HTTPException(
            status_code=503,
            detail="SMC analysis failed — see server logs.",
        )

    # score_confluence uses RSI/EMA from the finest available timeframe bars.
    indicator_bars = (
        ohlcv_map.get("M5")
        or ohlcv_map.get("M15")
        or ohlcv_map.get("H1")
        or next(iter(ohlcv_map.values()))
    )
    try:
        cr = _smc.score_confluence(mtf, indicator_bars, current_price)
    except Exception as exc:
        logger.error(
            "smc.confluence: score_confluence failed for %s — %s", pair, exc
        )
        raise HTTPException(
            status_code=503,
            detail="SMC confluence scoring failed — see server logs.",
        )

    return ConfluenceResultOut(
        pair=pair,
        score=cr.score,
        bias=cr.bias.value,
        factors=[
            ConfluenceFactorOut(
                name=f.name,
                score=f.score,
                max_score=f.max_score,
                confirmed=f.confirmed,
                reason=f.reason,
            )
            for f in cr.factors
        ],
        confirmed_count=cr.confirmed_count,
        total_factors=cr.total_factors,
        analysed_at=cr.analysed_at,
    )
