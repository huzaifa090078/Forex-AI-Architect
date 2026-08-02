"""
AI Engine — base implementations with shared scaffolding.
Concrete engines extend these and fill in the abstract methods.
"""

import logging
from typing import Any, Dict, List

from app.modules.ai_engine.interfaces import IAIEngine, IFeatureExtractor, ISignalFilter
from app.modules.ai_engine.types import OHLCV, FeatureVector, SignalCandidate, ModelMetadata
from app.core.config import settings

logger = logging.getLogger(__name__)


class BaseFeatureExtractor(IFeatureExtractor):
    """
    Shared feature-extraction scaffolding.
    Override `extract` to add domain-specific features.
    """

    def extract(self, ohlcv: List[OHLCV], context: Dict[str, Any]) -> FeatureVector:
        raise NotImplementedError(
            "Implement feature extraction in a concrete subclass. "
            "Features should include OHLCV derivatives, SMC structures, "
            "and indicator values from the Indicators module."
        )


class BaseSignalFilter(ISignalFilter):
    """
    Filters signal candidates by confidence threshold and deduplicates.
    Override `apply` to add additional filters (news suppression, correlation, etc.).
    """

    def apply(
        self,
        candidates: List[SignalCandidate],
        context: Dict[str, Any],
    ) -> List[SignalCandidate]:
        min_confidence = settings.AI_MIN_CONFIDENCE
        filtered = [c for c in candidates if c.confidence >= min_confidence]
        logger.debug(
            "SignalFilter: %d candidates → %d after confidence filter (min=%.2f)",
            len(candidates),
            len(filtered),
            min_confidence,
        )
        return filtered


class BaseAIEngine(IAIEngine):
    """
    Base AI Engine wiring feature extraction → inference → filtering.
    Subclass and inject concrete IModelInference and IFeatureExtractor implementations.
    """

    def __init__(
        self,
        extractor: IFeatureExtractor,
        filter_: ISignalFilter,
    ) -> None:
        self._extractor = extractor
        self._filter = filter_

    async def generate_signals(
        self,
        pair: str,
        timeframe: str,
        ohlcv: List[OHLCV],
        context: Dict[str, Any],
    ) -> List[SignalCandidate]:
        raise NotImplementedError(
            "Inject a concrete IModelInference and implement `generate_signals` "
            "to run: extractor.extract → model.predict → filter.apply → return."
        )
