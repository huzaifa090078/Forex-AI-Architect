"""
Market Scanner — base implementation scaffold.
"""

import logging
from typing import List, Optional

from app.modules.market_scanner.interfaces import IMarketScanner, IMarketDataProvider, ScanResult

logger = logging.getLogger(__name__)


class BaseMarketScanner(IMarketScanner):
    """
    Iterates over configured pairs, fetches OHLCV data, delegates structure
    detection to the SMC module and indicator checks to the Indicators module,
    and scores each result.
    """

    def __init__(self, data_provider: IMarketDataProvider) -> None:
        self._provider = data_provider

    async def scan_all(self, pairs: List[str]) -> List[ScanResult]:
        results: List[ScanResult] = []
        for pair in pairs:
            result = await self.scan_pair(pair)
            if result is not None:
                results.append(result)
        results.sort(key=lambda r: r.score, reverse=True)
        logger.info("MarketScanner: scanned %d pairs, found %d opportunities", len(pairs), len(results))
        return results

    async def scan_pair(self, pair: str) -> Optional[ScanResult]:
        raise NotImplementedError(
            "Implement scan_pair: fetch OHLCV → detect SMC structures → "
            "confirm with indicators → compute score → return ScanResult or None."
        )
