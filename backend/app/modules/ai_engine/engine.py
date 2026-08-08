"""
AI Decision Engine — Rule-Based Concrete Implementation.

RuleBasedAIEngine implements IDecisionEngine and derives a deterministic
TradeDecision from pre-computed SMC, indicator, and market-scanner inputs.

Architecture constraints (enforced by design, not by a guard):
  - Never calls MT5, SMCAnalyzer, IndicatorSuite, or any data source.
  - Never calls Risk Manager or Trade Manager.
  - All inputs supplied by the API orchestration layer (app/api/v1/ai.py).
  - Same inputs → same output every time (pure transformation).

The existing ML scaffold (IAIEngine, BaseAIEngine, IFeatureExtractor,
IModelInference) is preserved as-is in interfaces.py and base.py.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.modules.ai_engine.interfaces import IDecisionEngine
from app.modules.ai_engine.types import (
    IndicatorSummary,
    SMCSummary,
    TradeAction,
    TradeDecision,
    TradeQuality,
)
from app.modules.indicators.interfaces import IndicatorResult
from app.modules.market_scanner.interfaces import ScanResult
from app.modules.smc.interfaces import (
    ConfluenceResult,
    MTFAnalysis,
    TrendBias,
)

logger = logging.getLogger(__name__)

# ── Confidence weight constants ───────────────────────────────────────────────
# Weights sum to 1.0. Named constants — not in config (per Section 7 decision).
_W_SMC     = 0.35   # SMC confluence component  (0–100 score → 0.0–1.0)
_W_IND     = 0.30   # Technical indicator directional agreement
_W_MTF     = 0.20   # Multi-timeframe structural alignment score
_W_VOLUME  = 0.08   # Volume context (High / Normal / Low Volume)
_W_SESSION = 0.07   # Session quality (London > Asian > Sydney)

# ── Trade quality thresholds (confidence boundaries) ─────────────────────────
# Not in config (per Section 7 decision). Aligned with AI_MIN_CONFIDENCE = 0.75.
_Q_EXCELLENT = 0.90
_Q_GOOD      = 0.82
_Q_AVERAGE   = 0.75   # matches settings.AI_MIN_CONFIDENCE default
_Q_WEAK      = 0.65

# ── SL sizing multiplier ──────────────────────────────────────────────────────
# Hardcoded at 1.5× ATR per Section 7 decision (not in config).
_SL_ATR_MULT = 1.5

# ── Directional indicators used for agreement scoring ────────────────────────
# These five carry a directional signal field ("buy" | "sell" | "neutral").
_DIRECTIONAL_INDS = ["RSI_14", "MACD", "STOCH_RSI", "BB_20", "VWAP"]


class RuleBasedAIEngine(IDecisionEngine):
    """
    Deterministic confluence-based AI Decision Engine.

    Reads pre-computed SMC, indicator, and scanner inputs; returns a single
    TradeDecision per call. No external I/O, no mutable state.
    """

    # ── Public interface ──────────────────────────────────────────────────────

    async def evaluate(
        self,
        scan_result: ScanResult,
        indicators:  Dict[str, IndicatorResult],
        mtf:         Optional[MTFAnalysis],
        confluence:  Optional[ConfluenceResult],
        ohlcv:       List[Dict[str, Any]],
    ) -> TradeDecision:
        """
        Derive a TradeDecision from pre-computed inputs.
        Deterministic: same inputs always produce the same output.
        """
        now = datetime.now(timezone.utc)

        smc_bias = confluence.bias if confluence is not None else TrendBias.NEUTRAL
        mtf_bias = mtf.bias        if mtf        is not None else TrendBias.NEUTRAL
        scan_dir = scan_result.direction  # "buy" | "sell" | "ranging"

        # Step 1: directional vote (2 of 3 sources must agree)
        direction_hint = self._vote_direction(smc_bias, mtf_bias, scan_dir)

        # Step 2: compute individual confidence components
        smc_component               = self._smc_component(confluence)
        ind_component, ind_summaries = self._indicator_component(indicators, direction_hint)
        mtf_component               = self._mtf_component(mtf)
        vol_component               = self._volume_component(scan_result.volume_status)
        sess_component              = self._session_component(scan_result.session)

        # Spread in pips — prefer metadata["spread_pips"], fall back to spread field
        spread_pips: float = float(scan_result.metadata.get("spread_pips", 0.0) or 0.0)
        if spread_pips == 0.0 and scan_result.spread is not None:
            spread_pips = float(scan_result.spread)

        spread_penalty     = self._spread_penalty(spread_pips)
        volatility_penalty = self._volatility_penalty(scan_result.volatility_status)

        raw_confidence = (
            _W_SMC     * smc_component  +
            _W_IND     * ind_component  +
            _W_MTF     * mtf_component  +
            _W_VOLUME  * vol_component  +
            _W_SESSION * sess_component
        )
        confidence = min(1.0, max(0.0,
            raw_confidence * spread_penalty * volatility_penalty
        ))

        # Quality is computed before the NO_TRADE gate so the dashboard can
        # display "Weak — spread too high" rather than just "Rejected".
        trade_quality = self._classify_quality(confidence)

        # Step 3: collect all explicit rejection conditions (no early exit)
        rejection_reasons = self._check_rejection_conditions(
            scan_result    = scan_result,
            direction_hint = direction_hint,
            smc_bias       = smc_bias,
            mtf            = mtf,
            indicators     = indicators,
            spread_pips    = spread_pips,
        )

        # Step 4: apply final action gate
        if rejection_reasons:
            action = TradeAction.NO_TRADE
        elif confidence < settings.AI_MIN_CONFIDENCE:
            action = TradeAction.NO_TRADE
            rejection_reasons.append(
                f"Confidence {confidence:.0%} is below the minimum threshold "
                f"{settings.AI_MIN_CONFIDENCE:.0%}"
            )
        elif direction_hint == "buy":
            action = TradeAction.BUY
        elif direction_hint == "sell":
            action = TradeAction.SELL
        else:
            action = TradeAction.NO_TRADE
            rejection_reasons.append(
                "Directional conflict — SMC bias, MTF bias, and scanner "
                "direction do not reach a 2-of-3 majority"
            )

        # Step 5: entry / SL / TP candidates (only for actionable decisions)
        entry_price:     Optional[float] = None
        entry_zone_low:  Optional[float] = None
        entry_zone_high: Optional[float] = None
        stop_loss:       Optional[float] = None
        take_profit_1:   Optional[float] = None
        take_profit_2:   Optional[float] = None

        if action in (TradeAction.BUY, TradeAction.SELL):
            entry_price = scan_result.current_price
            entry_zone_low, entry_zone_high = self._compute_entry_zone(
                action, scan_result.current_price, mtf
            )
            stop_loss = self._compute_sl(action, entry_price, indicators)
            if stop_loss is not None:
                take_profit_1, take_profit_2 = self._compute_tp(
                    action, entry_price, stop_loss
                )

        logger.debug(
            "RuleBasedAIEngine: %s/%s → %s  conf=%.3f  quality=%s  reasons=%d",
            scan_result.pair, scan_result.timeframe,
            action.value, confidence, trade_quality.value,
            len(rejection_reasons),
        )

        return TradeDecision(
            pair               = scan_result.pair,
            timeframe          = scan_result.timeframe,
            action             = action,
            confidence         = confidence,
            trade_quality      = trade_quality,
            trend              = scan_result.trend_status,
            smc_summary        = self._build_smc_summary(mtf, confluence),
            indicators_summary = ind_summaries,
            entry_price        = entry_price,
            entry_zone_low     = entry_zone_low,
            entry_zone_high    = entry_zone_high,
            stop_loss          = stop_loss,
            take_profit_1      = take_profit_1,
            take_profit_2      = take_profit_2,
            rejection_reasons  = rejection_reasons,
            evaluated_at       = now,
            metadata           = {
                "spread_pips":        round(spread_pips, 4),
                "session":            scan_result.session,
                "smc_component":      round(smc_component,      4),
                "ind_component":      round(ind_component,      4),
                "mtf_component":      round(mtf_component,      4),
                "vol_component":      round(vol_component,      4),
                "sess_component":     round(sess_component,     4),
                "spread_penalty":     round(spread_penalty,     4),
                "volatility_penalty": round(volatility_penalty, 4),
                "raw_confidence":     round(raw_confidence,     4),
            },
        )

    # ── Direction voting ──────────────────────────────────────────────────────

    @staticmethod
    def _vote_direction(
        smc_bias: TrendBias,
        mtf_bias: TrendBias,
        scan_dir: str,
    ) -> Optional[str]:
        """
        Require at least 2 of 3 sources to agree on a direction.
        Returns "buy", "sell", or None (conflict / no majority).
        """
        buy_votes = (
            (1 if smc_bias == TrendBias.BULLISH else 0) +
            (1 if mtf_bias == TrendBias.BULLISH else 0) +
            (1 if scan_dir == "buy"             else 0)
        )
        sell_votes = (
            (1 if smc_bias == TrendBias.BEARISH else 0) +
            (1 if mtf_bias == TrendBias.BEARISH else 0) +
            (1 if scan_dir == "sell"            else 0)
        )
        if buy_votes >= 2:
            return "buy"
        if sell_votes >= 2:
            return "sell"
        return None

    # ── Confidence components ─────────────────────────────────────────────────

    @staticmethod
    def _smc_component(confluence: Optional[ConfluenceResult]) -> float:
        """Normalise the 0–100 SMC confluence score to 0.0–1.0."""
        if confluence is None:
            return 0.0
        return min(1.0, max(0.0, confluence.score / 100.0))

    @staticmethod
    def _indicator_component(
        indicators:     Dict[str, IndicatorResult],
        direction_hint: Optional[str],
    ) -> Tuple[float, List[IndicatorSummary]]:
        """
        Score directional agreement across the five primary directional indicators.

        Scoring per active indicator:
          signal == direction_hint  → 1.0
          signal == "neutral"/None  → 0.5
          signal == opposite        → 0.0
          status != "active"        → excluded from average denominator

        ADX bonus: +0.10 when ADX is trending and DI is aligned with direction;
                   +0.05 when ADX is trending but DI is unknown; capped at 1.0.

        Returns (component 0.0–1.0, full IndicatorSummary list for all indicators).
        """
        opposite = (
            "sell" if direction_hint == "buy"
            else ("buy" if direction_hint == "sell" else None)
        )
        scores: List[float] = []

        for name in _DIRECTIONAL_INDS:
            result = indicators.get(name)
            if result is None or result.status != "active":
                continue   # exclude from denominator — do not penalise
            if direction_hint is None:
                scores.append(0.5)
            elif result.signal == direction_hint:
                scores.append(1.0)
            elif result.signal == "neutral" or result.signal is None:
                scores.append(0.5)
            elif result.signal == opposite:
                scores.append(0.0)
            else:
                scores.append(0.5)   # unexpected value → treat as neutral

        ind_score = float(sum(scores) / len(scores)) if scores else 0.0

        # ADX trend-strength bonus
        adx = indicators.get("ADX_14")
        if adx is not None and adx.status == "active" and adx.metadata:
            trending   = adx.metadata.get("trending", False)
            di_bullish = adx.metadata.get("di_bullish", None)
            if trending:
                if direction_hint is None:
                    ind_score = min(1.0, ind_score + 0.05)
                elif direction_hint == "buy" and di_bullish is True:
                    ind_score = min(1.0, ind_score + 0.10)
                elif direction_hint == "sell" and di_bullish is False:
                    ind_score = min(1.0, ind_score + 0.10)
                else:
                    ind_score = min(1.0, ind_score + 0.05)

        # Build summary list for all available indicators
        summaries: List[IndicatorSummary] = [
            IndicatorSummary(
                name   = name,
                signal = result.signal,
                value  = result.value,
                status = result.status,
            )
            for name, result in indicators.items()
            if result is not None
        ]

        return ind_score, summaries

    @staticmethod
    def _mtf_component(mtf: Optional[MTFAnalysis]) -> float:
        """Use MTFAnalysis.alignment_score directly (already 0.0–1.0)."""
        if mtf is None:
            return 0.0
        return min(1.0, max(0.0, mtf.alignment_score))

    @staticmethod
    def _volume_component(volume_status: str) -> float:
        if "High" in volume_status:
            return 1.0
        if "Normal" in volume_status:
            return 0.6
        return 0.2   # "Low Volume" or unknown

    @staticmethod
    def _session_component(session: str) -> float:
        _high = {"New York", "London", "London/New York Overlap", "London/New York"}
        if session in _high:
            return 1.0
        if session == "Asian":
            return 0.5
        return 0.2   # Sydney / Unknown / weekend

    @staticmethod
    def _spread_penalty(spread_pips: float) -> float:
        """
        Linear decay from 1.0 → 0.75 as spread approaches AI_MAX_SPREAD_PIPS.
        Spread above the threshold is gated by rejection_reasons, not this multiplier.
        """
        threshold = settings.AI_MAX_SPREAD_PIPS
        if spread_pips <= 0:
            return 1.0
        if spread_pips <= threshold * 0.5:
            return 1.0
        if spread_pips <= threshold:
            ratio = (spread_pips - threshold * 0.5) / (threshold * 0.5)
            return 1.0 - 0.25 * ratio
        return 0.75   # above threshold; rejection_reasons handles the hard gate

    @staticmethod
    def _volatility_penalty(volatility_status: str) -> float:
        """Penalise confidence when high-volatility filter is enabled."""
        if settings.AI_VOLATILITY_FILTER_ENABLED and volatility_status == "High":
            return 0.7
        return 1.0

    # ── Quality classification ────────────────────────────────────────────────

    @staticmethod
    def _classify_quality(confidence: float) -> TradeQuality:
        if confidence >= _Q_EXCELLENT:
            return TradeQuality.EXCELLENT
        if confidence >= _Q_GOOD:
            return TradeQuality.GOOD
        if confidence >= _Q_AVERAGE:
            return TradeQuality.AVERAGE
        if confidence >= _Q_WEAK:
            return TradeQuality.WEAK
        return TradeQuality.REJECT

    # ── Rejection condition checks ────────────────────────────────────────────

    @staticmethod
    def _check_rejection_conditions(
        scan_result:    ScanResult,
        direction_hint: Optional[str],
        smc_bias:       TrendBias,
        mtf:            Optional[MTFAnalysis],
        indicators:     Dict[str, IndicatorResult],
        spread_pips:    float,
    ) -> List[str]:
        """
        Collect all explicit rejection reasons.
        All conditions are checked — no early exit (full audit trail).
        """
        reasons: List[str] = []

        # 1. Spread gate
        if spread_pips > settings.AI_MAX_SPREAD_PIPS:
            reasons.append(
                f"Spread {spread_pips:.1f} pips exceeds the maximum "
                f"{settings.AI_MAX_SPREAD_PIPS:.1f} pips"
            )

        # 2. No directional majority
        if direction_hint is None:
            reasons.append(
                "No directional majority — SMC bias, MTF bias, and scanner "
                "direction do not reach a 2-of-3 majority"
            )

        # 3. Neutral SMC with low MTF alignment
        if smc_bias == TrendBias.NEUTRAL:
            alignment = mtf.alignment_score if mtf is not None else 0.0
            if alignment < 0.5:
                reasons.append(
                    f"SMC bias is NEUTRAL with low MTF alignment "
                    f"({alignment:.2f} < 0.50)"
                )

        # 4. Indicator directional conflict (≥ 3 of 5 active indicators oppose direction_hint)
        if direction_hint is not None:
            opposite = "sell" if direction_hint == "buy" else "buy"
            opposite_count = sum(
                1
                for name in _DIRECTIONAL_INDS
                if (r := indicators.get(name)) is not None
                and r.status == "active"
                and r.signal == opposite
            )
            if opposite_count >= 3:
                reasons.append(
                    f"Indicator conflict — {opposite_count}/5 directional indicators "
                    f"signal '{opposite}' against direction '{direction_hint}'"
                )

        # 5. Volatility filter (when enabled)
        if (
            settings.AI_VOLATILITY_FILTER_ENABLED
            and scan_result.volatility_status == "High"
        ):
            reasons.append(
                "High volatility setup rejected (AI_VOLATILITY_FILTER_ENABLED=True)"
            )

        # 6. Session filter (when a restricted list is configured)
        if (
            settings.AI_TRADEABLE_SESSIONS
            and scan_result.session not in settings.AI_TRADEABLE_SESSIONS
        ):
            reasons.append(
                f"Session '{scan_result.session}' is not in the allowed sessions list "
                f"{settings.AI_TRADEABLE_SESSIONS}"
            )

        return reasons

    # ── Entry zone ────────────────────────────────────────────────────────────

    @staticmethod
    def _compute_entry_zone(
        action:        TradeAction,
        current_price: float,
        mtf:           Optional[MTFAnalysis],
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Find the nearest Order Block or FVG aligned with the trade direction.
        Searches M15 then H1 timeframes.

        For BUY:  demand zones (bullish structures) below current price.
        For SELL: supply zones (bearish structures) above current price.

        Returns (zone_low, zone_high) or (None, None) when no zone found.
        """
        if mtf is None:
            return None, None

        direction_str = "bullish" if action == TradeAction.BUY else "bearish"

        for tf_name in ("M15", "H1"):
            tf_data = mtf.timeframes.get(tf_name)
            if tf_data is None:
                continue

            candidates: List[Tuple[float, float]] = []

            for ob in tf_data.order_blocks:
                if ob.direction != direction_str:
                    continue
                if action == TradeAction.BUY and ob.price_high < current_price:
                    candidates.append((ob.price_low, ob.price_high))
                elif action == TradeAction.SELL and ob.price_low > current_price:
                    candidates.append((ob.price_low, ob.price_high))

            for fvg in tf_data.fvgs:
                if fvg.direction != direction_str:
                    continue
                if action == TradeAction.BUY and fvg.price_high < current_price:
                    candidates.append((fvg.price_low, fvg.price_high))
                elif action == TradeAction.SELL and fvg.price_low > current_price:
                    candidates.append((fvg.price_low, fvg.price_high))

            if candidates:
                if action == TradeAction.BUY:
                    # Closest below = highest price_high
                    best = max(candidates, key=lambda z: z[1])
                else:
                    # Closest above = lowest price_low
                    best = min(candidates, key=lambda z: z[0])
                return best[0], best[1]

        return None, None

    # ── Stop Loss candidate ───────────────────────────────────────────────────

    @staticmethod
    def _compute_sl(
        action:     TradeAction,
        entry:      float,
        indicators: Dict[str, IndicatorResult],
    ) -> Optional[float]:
        """
        ATR-based stop loss candidate: entry ± (_SL_ATR_MULT × ATR_14).
        Returns None when ATR_14 is not active or its value is zero/invalid.
        Risk Manager finalises the actual SL in a later section.
        """
        atr_result = indicators.get("ATR_14")
        if atr_result is None or atr_result.status != "active":
            return None
        try:
            atr = float(atr_result.value)
        except (TypeError, ValueError):
            return None
        if atr <= 0:
            return None

        if action == TradeAction.BUY:
            return round(entry - _SL_ATR_MULT * atr, 5)
        return round(entry + _SL_ATR_MULT * atr, 5)

    # ── Take Profit candidates ────────────────────────────────────────────────

    @staticmethod
    def _compute_tp(
        action: TradeAction,
        entry:  float,
        sl:     float,
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Take-profit candidates at 1:1 and 1:2 risk-reward ratios.
        Risk Manager finalises these in a later section.
        """
        risk = abs(entry - sl)
        if risk <= 0:
            return None, None

        if action == TradeAction.BUY:
            return round(entry + risk * 1.0, 5), round(entry + risk * 2.0, 5)
        return round(entry - risk * 1.0, 5), round(entry - risk * 2.0, 5)

    # ── SMC summary builder ───────────────────────────────────────────────────

    @staticmethod
    def _build_smc_summary(
        mtf:        Optional[MTFAnalysis],
        confluence: Optional[ConfluenceResult],
    ) -> Optional[SMCSummary]:
        if mtf is None and confluence is None:
            return None

        if confluence is not None:
            bias = confluence.bias.value
        elif mtf is not None:
            bias = mtf.bias.value
        else:
            bias = TrendBias.NEUTRAL.value

        return SMCSummary(
            bias                   = bias,
            alignment_score        = mtf.alignment_score        if mtf        is not None else 0.0,
            confluence_score       = confluence.score           if confluence is not None else 0,
            dominant_timeframe     = mtf.dominant_timeframe     if mtf        is not None else "",
            confirmed_factors      = [f.name for f in confluence.factors if f.confirmed]
                                     if confluence is not None else [],
            conflicting_timeframes = mtf.conflicting_timeframes if mtf        is not None else [],
        )
