"""
AI Engine — shared data types.
Pure dataclasses; no business logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
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
