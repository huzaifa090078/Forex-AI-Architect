# Market Scanner — multi-pair opportunity detection
#
# Public API for the Market Scanner package.
# Section 3 additions (live feed, validation) are exported alongside the
# pre-existing scanner and data-provider components so that any module can
# import from the package root without knowing its internal layout.

from app.modules.market_scanner.interfaces import (
    IMarketScanner,
    IMarketDataProvider,
    ScanResult,
)
from app.modules.market_scanner.base import BaseMarketScanner
from app.modules.market_scanner.market_data_service import MarketDataService
from app.modules.market_scanner.scanner import MarketScanner, FOREX_PAIRS, TIMEFRAMES

# ── Section 3: Live Data Feed ─────────────────────────────────────────────────
from app.modules.market_scanner.live_feed import MarketDataFeed, market_data_feed

# ── Section 3: Validation Layer ───────────────────────────────────────────────
from app.modules.market_scanner.validation import (
    validate_bar,
    validate_bars,
    validate_tick,
    BarValidationError,
    TickValidationError,
)

__all__ = [
    # Interfaces & data contracts
    "IMarketScanner",
    "IMarketDataProvider",
    "ScanResult",
    # Base / concrete scanner
    "BaseMarketScanner",
    "MarketScanner",
    # Data service
    "MarketDataService",
    # Configuration constants
    "FOREX_PAIRS",
    "TIMEFRAMES",
    # Section 3 — live feed
    "MarketDataFeed",
    "market_data_feed",
    # Section 3 — validation
    "validate_bar",
    "validate_bars",
    "validate_tick",
    "BarValidationError",
    "TickValidationError",
]
