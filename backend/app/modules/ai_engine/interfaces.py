"""
AI Engine — abstract interface contracts.

Any model backend (scikit-learn, PyTorch, ONNX, etc.) must implement
these interfaces. This keeps the rest of the system decoupled from the
specific AI framework in use.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.modules.ai_engine.types import (
    OHLCV,
    FeatureVector,
    SignalCandidate,
    ModelMetadata,
    TradeDecision,
)


class IFeatureExtractor(ABC):
    """Transform raw OHLCV + indicator data into a model-ready feature vector."""

    @abstractmethod
    def extract(self, ohlcv: List[OHLCV], context: Dict[str, Any]) -> FeatureVector:
        """
        Extract features from a candle series and any contextual data
        (SMC structures, indicator values, news sentiment scores, etc.).
        """
        ...


class IModelInference(ABC):
    """Run inference on a feature vector and produce signal candidates."""

    @abstractmethod
    def predict(self, features: FeatureVector) -> List[SignalCandidate]:
        """
        Return a ranked list of signal candidates with confidence scores.
        The caller is responsible for applying the minimum-confidence threshold.
        """
        ...

    @abstractmethod
    def load(self, model_path: str) -> None:
        """Load model weights / artifacts from disk."""
        ...

    @abstractmethod
    def metadata(self) -> ModelMetadata:
        """Return descriptive metadata about the loaded model."""
        ...


class ISignalFilter(ABC):
    """Post-process raw signal candidates before they are persisted."""

    @abstractmethod
    def apply(
        self,
        candidates: List[SignalCandidate],
        context: Dict[str, Any],
    ) -> List[SignalCandidate]:
        """
        Filter, re-rank, or enrich candidates.
        Implementations may apply news suppression, duplicate elimination,
        correlation checks, or regime filtering.
        """
        ...


class IAIEngine(ABC):
    """
    Top-level AI Engine facade.
    Orchestrates: feature extraction → model inference → signal filtering.
    Reserved for future ML inference; preserved as-is from the ML scaffold.
    """

    @abstractmethod
    async def generate_signals(
        self,
        pair: str,
        timeframe: str,
        ohlcv: List[OHLCV],
        context: Dict[str, Any],
    ) -> List[SignalCandidate]:
        """
        Full pipeline: extract features, run inference, filter, return signals.
        This is the primary entry point called by the Market Scanner.
        """
        ...


# ── Section 7: Rule-Based Decision Engine interface ───────────────────────────
# Distinct from IAIEngine (ML scaffold above). IDecisionEngine receives
# fully pre-computed inputs from the API orchestration layer and returns
# a single TradeDecision. It never calls SMCAnalyzer, IndicatorSuite, MT5,
# Risk Manager, or any data source.

class IDecisionEngine(ABC):
    """
    Rule-based confluence decision interface.

    The API layer is responsible for fetching data and pre-computing all
    inputs (ScanResult, indicators, MTFAnalysis, ConfluenceResult).
    The engine evaluates those inputs deterministically and returns one
    TradeDecision per call. Same inputs → same output every time.
    """

    @abstractmethod
    async def evaluate(
        self,
        scan_result: "ScanResult",         # type: ignore[name-defined]
        indicators:  Dict[str, Any],       # Dict[str, IndicatorResult]
        mtf:         Optional[Any],        # Optional[MTFAnalysis]
        confluence:  Optional[Any],        # Optional[ConfluenceResult]
        ohlcv:       List[Dict[str, Any]], # primary-timeframe bars (for future use)
    ) -> TradeDecision:
        """
        Derive a TradeDecision from fully pre-computed inputs.

        Must never call SMCAnalyzer, IndicatorSuite, MarketDataService,
        Risk Manager, Trade Manager, or any MT5 connector.
        All inputs are provided by the caller.
        """
        ...
