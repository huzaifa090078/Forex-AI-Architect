"""
AI Engine — shared data types.
Pure dataclasses; no business logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass
class OHLCV:
    """A single OHLCV candlestick."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class FeatureVector:
    """Flat feature vector fed into the model."""
    pair: str
    timeframe: str
    values: List[float]
    feature_names: List[str]
    computed_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SignalCandidate:
    """Raw signal output from model inference before filtering/persistence."""
    pair: str
    direction: str                     # "buy" | "sell"
    confidence: float                  # 0.0 – 1.0
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    smc_pattern: Optional[str] = None
    indicators: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelMetadata:
    """Descriptive information about a loaded AI model."""
    name: str
    version: str
    framework: str                     # "sklearn" | "pytorch" | "onnx" | etc.
    trained_at: Optional[datetime] = None
    pairs: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=list)
    feature_count: int = 0
    notes: str = ""


# ── Section 7: Rule-Based AI Decision Engine types ────────────────────────────

class TradeAction(str, Enum):
    """Deterministic action produced by the AI Decision Engine."""
    BUY      = "buy"
    SELL     = "sell"
    NO_TRADE = "no_trade"


class TradeQuality(str, Enum):
    """
    Qualitative classification of a trade setup.

    Boundaries correspond to confidence thresholds:
      EXCELLENT  ≥ 0.90
      GOOD       ≥ 0.82
      AVERAGE    ≥ 0.75  (minimum actionable — equals AI_MIN_CONFIDENCE default)
      WEAK       ≥ 0.65  (below threshold → NO_TRADE)
      REJECT     < 0.65
    """
    EXCELLENT = "excellent"
    GOOD      = "good"
    AVERAGE   = "average"
    WEAK      = "weak"
    REJECT    = "reject"


@dataclass
class IndicatorSummary:
    """Compact per-indicator result included in TradeDecision for dashboard output."""
    name:   str
    signal: Optional[str]   # "buy" | "sell" | "neutral" | None
    value:  Any             # scalar float or dict
    status: str             # "active" | "warmup" | "unavailable"


@dataclass
class SMCSummary:
    """Compact SMC summary embedded in TradeDecision."""
    bias:                   str        # TrendBias value: "bullish" | "bearish" | "neutral"
    alignment_score:        float      # 0.0 – 1.0 from MTFAnalysis
    confluence_score:       int        # 0 – 100 from ConfluenceResult
    dominant_timeframe:     str
    confirmed_factors:      List[str]  # names of ConfluenceFactors where confirmed=True
    conflicting_timeframes: List[str]


@dataclass
class TradeDecision:
    """
    Full output from the AI Decision Engine (rule-based phase).

    In-memory DTO — not persisted to the database in Section 7 (A3 decision).
    BUY/SELL decisions are compatible with IRiskManager.check_trade() for
    future Risk Manager integration. NO_TRADE decisions are never stored.

    Risk Manager boundary:
      stop_loss / take_profit_1 / take_profit_2 are *candidates* produced by
      ATR-based sizing. The Risk Manager finalises these in a later section.
    """
    pair:               str
    timeframe:          str
    action:             TradeAction
    confidence:         float                   # 0.0 – 1.0, clamped
    trade_quality:      TradeQuality
    trend:              str                     # "bullish" | "bearish" | "ranging"
    smc_summary:        Optional[SMCSummary]
    indicators_summary: List[IndicatorSummary]
    entry_price:        Optional[float]         # current price at decision time
    entry_zone_low:     Optional[float]         # better-entry zone lower bound
    entry_zone_high:    Optional[float]         # better-entry zone upper bound
    stop_loss:          Optional[float]         # candidate SL (Risk Manager finalises)
    take_profit_1:      Optional[float]         # candidate TP1 at 1:1 RR
    take_profit_2:      Optional[float]         # candidate TP2 at 1:2 RR
    rejection_reasons:  List[str]               # non-empty whenever action == NO_TRADE
    evaluated_at:       datetime
    metadata:           Dict[str, Any]          # spread_pips, session, raw component scores
