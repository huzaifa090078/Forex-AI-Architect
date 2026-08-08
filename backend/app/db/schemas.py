"""
Pydantic v2 schemas for API request/response validation.
Separate from ORM models — no SQLAlchemy imports here.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─── Auth ─────────────────────────────────────────────────────────────────────

class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1)


class RefreshInput(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    name: str
    role: str
    created_at: datetime


# ─── Dashboard ────────────────────────────────────────────────────────────────

class DashboardSummaryOut(BaseModel):
    balance: float
    equity: float
    total_pnl: float
    today_pnl: float
    open_trades: int
    total_trades: int
    win_rate: float
    bot_status: str                    # "running" | "paused" | "stopped" | "error"


class PerformancePointOut(BaseModel):
    date: str                          # ISO date string
    equity: float
    pnl: float
    trades: int


# ─── Trades ───────────────────────────────────────────────────────────────────

class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    pair: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    status: str
    pnl: Optional[float] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None
    risk_reward_ratio: Optional[float] = None
    notes: Optional[str] = None
    broker_order_id: Optional[str] = None
    signal_id: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime


class OpenTradeOut(BaseModel):
    """Live enriched open trade — includes current broker price/PnL where available."""
    id: str
    pair: str
    direction: str
    entry_price: float
    current_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    lot_size: float
    pnl: Optional[float] = None
    status: str
    opened_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    broker_ticket: Optional[str] = None
    sl_distance_pips: Optional[float] = None
    tp_distance_pips: Optional[float] = None
    risk_reward_ratio: Optional[float] = None


class ManualCloseIn(BaseModel):
    reason: str = "manual"


class ModifySlTpIn(BaseModel):
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class TradeExecutionResultOut(BaseModel):
    success: bool
    broker_order_id: Optional[str] = None
    fill_price: Optional[float] = None
    fill_time: Optional[datetime] = None
    error_message: Optional[str] = None


class TradeInput(BaseModel):
    pair: str
    direction: str                     # "buy" | "sell"
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    notes: Optional[str] = None
    signal_id: Optional[str] = None


class TradeUpdate(BaseModel):
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    lot_size: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None      # "closed" | "cancelled"
    pnl: Optional[float] = None
    closed_at: Optional[datetime] = None


class TradeStatsOut(BaseModel):
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    avg_rr: float


class PaginatedTradesOut(BaseModel):
    items: List[TradeOut]
    total: int
    page: int
    limit: int


# ─── Signals ──────────────────────────────────────────────────────────────────

class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    pair: str
    direction: str
    confidence: float
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    smc_pattern: Optional[str] = None
    indicators: List[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None


class PaginatedSignalsOut(BaseModel):
    items: List[SignalOut]
    total: int
    page: int
    limit: int


# ─── Market ───────────────────────────────────────────────────────────────────

class MarketPairOut(BaseModel):
    """
    Response schema for a live forex pair quote.
    Fields are aliased to camelCase to match the OpenAPI spec consumed by
    the Orval-generated frontend client.
    """
    model_config = ConfigDict(populate_by_name=True)

    symbol: str
    bid: float
    ask: float
    spread: float
    change_24h: float = Field(alias="change24h")
    volatility: Optional[float] = None
    trend: str                         # "bullish" | "bearish" | "ranging"
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")


class MarketOpportunityOut(BaseModel):
    """
    Response schema for a single market scanner opportunity.
    Fields are aliased to camelCase to match the OpenAPI spec consumed by
    the Orval-generated frontend client.
    """
    model_config = ConfigDict(populate_by_name=True)

    pair:              str
    direction:         str
    score:             float
    smc_pattern:       str            = Field(alias="smcPattern")
    timeframe:         str
    current_price:     float          = Field(alias="currentPrice")
    trend_status:      str            = Field(alias="trendStatus")
    volatility_status: str            = Field(alias="volatilityStatus")
    volume_status:     str            = Field(alias="volumeStatus")
    spread:            Optional[float] = None
    session:           str            = "Unknown"
    priority_level:    str            = Field(alias="priorityLevel")
    confluence_factors: List[str]     = Field(default_factory=list, alias="confluenceFactors")
    detected_at:       Optional[datetime] = Field(default=None, alias="detectedAt")


# ─── Backtests ────────────────────────────────────────────────────────────────

class BacktestInput(BaseModel):
    strategy_id: str
    pair: str
    from_date: str                     # ISO date
    to_date: str
    initial_balance: float
    lot_size: float
    risk_per_trade: Optional[float] = 1.0


class BacktestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    strategy_id: str
    pair: str
    from_date: str
    to_date: str
    status: str
    initial_balance: Optional[float] = None
    final_balance: Optional[float] = None
    total_trades: Optional[int] = None
    winning_trades: Optional[int] = None
    losing_trades: Optional[int] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    max_drawdown: Optional[float] = None
    net_pnl: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


# ─── News (Section 10) ────────────────────────────────────────────────────────

class NewsItemOut(BaseModel):
    """Legacy schema kept for backward compat — maps news_items table."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    headline: str
    source: str
    impact: str
    currency: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    published_at: datetime


class NewsEventOut(BaseModel):
    """Full Section 10 news event — maps news_events table."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    provider: str
    event_name: str
    currency: str
    impact: str
    event_time: datetime
    source: Optional[str] = None
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    status: str
    # Computed fields (not stored)
    affected_pairs: List[str] = Field(default_factory=list)
    minutes_to_event: Optional[float] = None


class PairNewsStatusOut(BaseModel):
    """Result of evaluate_pair() — trading safety status for a single pair."""
    pair: str
    affected: bool
    blocked: bool
    reason: str
    impact: Optional[str] = None
    event_name: Optional[str] = None
    event_time: Optional[datetime] = None
    minutes_to_event: Optional[float] = None
    status: Optional[str] = None
    provider_ok: bool = True


class NewsSystemStatusOut(BaseModel):
    """Overall news filter system status for the dashboard."""
    provider_available: bool
    last_refresh: Optional[datetime] = None
    filter_enabled: bool
    high_impact_enabled: bool
    medium_impact_enabled: bool
    low_impact_enabled: bool
    pause_before_minutes: int
    resume_after_minutes: int
    cached_event_count: int
    high_impact_count: int


# ─── Settings ─────────────────────────────────────────────────────────────────

class BotSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    risk_per_trade: float
    max_open_trades: int
    max_daily_loss: float
    allowed_pairs: List[str]
    trading_enabled: bool
    news_filter_enabled: bool
    mt5_connected: bool = False
    mt5_account: Optional[str] = None
    mt5_server: Optional[str] = None
    min_confidence: float
    default_lot_size: float


class BotSettingsUpdate(BaseModel):
    risk_per_trade: Optional[float] = None
    max_open_trades: Optional[int] = None
    max_daily_loss: Optional[float] = None
    allowed_pairs: Optional[List[str]] = None
    trading_enabled: Optional[bool] = None
    news_filter_enabled: Optional[bool] = None
    mt5_account: Optional[str] = None
    mt5_server: Optional[str] = None
    min_confidence: Optional[float] = None
    default_lot_size: Optional[float] = None


# ─── Logs ─────────────────────────────────────────────────────────────────────

class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    level: str
    module: str
    message: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class PaginatedLogsOut(BaseModel):
    items: List[LogEntryOut]
    total: int
    page: int
    limit: int


# ─── SMC ──────────────────────────────────────────────────────────────────────

class SMCStructureOut(BaseModel):
    """
    Response schema for a single detected SMC structure.

    Covers all pattern types: BOS, CHoCH, Order Block, Breaker Block,
    Fair Value Gap, Imbalance, Liquidity Sweep, Supply Zone, Demand Zone,
    Mitigation Block, and Inducement.

    ``zone`` reports whether price was in a Premium, Equilibrium, or Discount
    area when the structure was detected.
    ``strength`` is a 0.0–1.0 confidence score produced by the SMC engine.
    ``validated`` is True when the structure has been subsequently confirmed
    by a price reaction at the level.
    """
    model_config = ConfigDict(populate_by_name=True)

    pattern:     str
    pair:        str
    timeframe:   str
    zone:        str                           # "premium" | "equilibrium" | "discount"
    price_low:   float = Field(alias="priceLow")
    price_high:  float = Field(alias="priceHigh")
    direction:   str                           # "bullish" | "bearish"
    strength:    float
    validated:   bool = False
    detected_at: Optional[datetime] = Field(default=None, alias="detectedAt")
    metadata:    Dict[str, Any]     = Field(default_factory=dict)


class ConfluenceFactorOut(BaseModel):
    """
    Response schema for one scored component within a confluence result.

    ``name``      — machine-readable factor identifier
                    (e.g. ``"order_block_alignment"``).
    ``score``     — points this factor contributed (0 – max_score).
    ``max_score`` — maximum possible contribution from this factor.
    ``confirmed`` — True when score > 0 (factor fired in the expected direction).
    ``reason``    — one-sentence human-readable explanation of the result.
    """
    model_config = ConfigDict(populate_by_name=True)

    name:      str
    score:     float
    max_score: float = Field(alias="maxScore")
    confirmed: bool
    reason:    str


# ─── AI Decision Engine ───────────────────────────────────────────────────────

class IndicatorSummaryOut(BaseModel):
    """
    Compact per-indicator result included in TradeDecisionOut.
    ``value`` may be a scalar float or a nested dict (e.g. MACD histogram dict).
    """
    model_config = ConfigDict(populate_by_name=True)

    name:   str
    signal: Optional[str] = None         # "buy" | "sell" | "neutral" | None
    value:  Any                           # scalar or dict
    status: str                           # "active" | "warmup" | "unavailable"


class SMCSummaryOut(BaseModel):
    """Compact SMC analysis summary embedded in TradeDecisionOut."""
    model_config = ConfigDict(populate_by_name=True)

    bias:                   str
    alignment_score:        float     = Field(alias="alignmentScore")
    confluence_score:       int       = Field(alias="confluenceScore")
    dominant_timeframe:     str       = Field(alias="dominantTimeframe")
    confirmed_factors:      List[str] = Field(alias="confirmedFactors")
    conflicting_timeframes: List[str] = Field(alias="conflictingTimeframes")


class TradeDecisionOut(BaseModel):
    """
    Response schema for a single AI Decision Engine evaluation result.

    BUY / SELL / NO_TRADE is returned for every evaluation request.
    ``rejectionReasons`` is non-empty whenever action == "no_trade".
    ``stopLoss``, ``takeProfit1``, ``takeProfit2`` are *candidate* values;
    the Risk Manager finalises them in a later section.
    """
    model_config = ConfigDict(populate_by_name=True)

    pair:               str
    timeframe:          str
    action:             str                            # "buy" | "sell" | "no_trade"
    confidence:         float                          # 0.0 – 1.0
    trade_quality:      str   = Field(alias="tradeQuality")
    trend:              str
    smc_summary:        Optional[SMCSummaryOut] = Field(default=None, alias="smcSummary")
    indicators_summary: List[IndicatorSummaryOut] = Field(
        default_factory=list, alias="indicatorsSummary"
    )
    entry_price:        Optional[float] = Field(default=None, alias="entryPrice")
    entry_zone_low:     Optional[float] = Field(default=None, alias="entryZoneLow")
    entry_zone_high:    Optional[float] = Field(default=None, alias="entryZoneHigh")
    stop_loss:          Optional[float] = Field(default=None, alias="stopLoss")
    take_profit_1:      Optional[float] = Field(default=None, alias="takeProfit1")
    take_profit_2:      Optional[float] = Field(default=None, alias="takeProfit2")
    rejection_reasons:  List[str]       = Field(default_factory=list, alias="rejectionReasons")
    evaluated_at:       datetime        = Field(alias="evaluatedAt")
    metadata:           Dict[str, Any]  = Field(default_factory=dict)


# ─── Risk Manager (Section 8) ─────────────────────────────────────────────────

class ProtectionStateOut(BaseModel):
    """Current active protection states exposed through the dashboard API."""
    model_config = ConfigDict(populate_by_name=True)

    daily_loss_active:        bool  = Field(alias="dailyLossActive")
    daily_profit_active:      bool  = Field(alias="dailyProfitActive")
    drawdown_active:          bool  = Field(alias="drawdownActive")
    consecutive_loss_active:  bool  = Field(alias="consecutiveLossActive")
    max_open_trades_active:   bool  = Field(alias="maxOpenTradesActive")
    session_blocked:          bool  = Field(alias="sessionBlocked")
    news_blocked:             bool  = Field(alias="newsBlocked")
    spread_blocked:           bool  = Field(alias="spreadBlocked")
    exposure_blocked:         bool  = Field(alias="exposureBlocked")
    any_active:               bool  = Field(alias="anyActive")

    daily_pnl:               float = Field(alias="dailyPnl")
    daily_pnl_pct:           float = Field(alias="dailyPnlPct")
    drawdown_pct:            float = Field(alias="drawdownPct")
    consecutive_losses:      int   = Field(alias="consecutiveLosses")
    open_trades:             int   = Field(alias="openTrades")


class RiskApprovalOut(BaseModel):
    """
    Response schema for a RuleBasedRiskManager.approve_trade() result.

    ``approved`` is True only when every mandatory Section 8 check passed.
    ``rejectionReasons`` lists all failures when approved=False.
    ``lotSize`` and ``riskAmount`` are 0.0 when rejected.
    """
    model_config = ConfigDict(populate_by_name=True)

    approved:           bool
    pair:               str
    direction:          str
    entry:              float
    stop_loss:          float   = Field(alias="stopLoss")
    take_profit:        float   = Field(alias="takeProfit")
    lot_size:           float   = Field(alias="lotSize")
    risk_amount:        float   = Field(alias="riskAmount")
    risk_pct:           float   = Field(alias="riskPct")
    rr_ratio:           float   = Field(alias="rrRatio")
    rejection_reasons:  List[str] = Field(alias="rejectionReasons")
    protection_flags:   List[str] = Field(alias="protectionFlags")
    approved_at:        datetime  = Field(alias="approvedAt")


class RiskStateOut(BaseModel):
    """
    Full Risk Manager dashboard state: configuration + protection + limits.
    """
    model_config = ConfigDict(populate_by_name=True)

    # Configuration
    risk_per_trade_pct:            float     = Field(alias="riskPerTradePct")
    min_rr:                        float     = Field(alias="minRr")
    max_open_trades:               int       = Field(alias="maxOpenTrades")
    max_daily_loss_pct:            float     = Field(alias="maxDailyLossPct")
    max_daily_profit_pct:          float     = Field(alias="maxDailyProfitPct")
    max_drawdown_pct:              float     = Field(alias="maxDrawdownPct")
    max_consecutive_losses:        int       = Field(alias="maxConsecutiveLosses")
    max_spread_pips:               float     = Field(alias="maxSpreadPips")
    allowed_sessions:              List[str] = Field(alias="allowedSessions")
    max_total_open_lots:           float     = Field(alias="maxTotalOpenLots")
    max_currency_exposure_lots:    float     = Field(alias="maxCurrencyExposureLots")

    # Live protection state
    protection:                    ProtectionStateOut


class RiskApprovalIn(BaseModel):
    """Request body for the pre-flight risk check endpoint."""
    pair:        str
    direction:   str     # "buy" | "sell"
    entry:       float
    stop_loss:   float
    take_profit: float


class RecordTradeCloseIn(BaseModel):
    """Request body for recording a closed trade P&L."""
    trade_id: str
    pnl:      float


class PositionSizeOut(BaseModel):
    """Computed position size output (legacy compute_position_size path)."""
    model_config = ConfigDict(populate_by_name=True)

    lot_size:          float = Field(alias="lotSize")
    risk_amount:       float = Field(alias="riskAmount")
    pip_value:         float = Field(alias="pipValue")
    stop_loss_pips:    float = Field(alias="stopLossPips")
    risk_reward_ratio: float = Field(alias="riskRewardRatio")


class ConfluenceResultOut(BaseModel):
    """
    Response schema for the normalized 0–100 SMC confluence score for a pair.

    Eight independent factors are evaluated (BOS/CHoCH alignment, Order Blocks,
    Fair Value Gaps, Liquidity Sweeps, Supply/Demand zones, Premium/Discount
    zone, RSI-14, and EMA-20). Their max scores sum to exactly 100.

    ``bias``            — overall directional bias inherited from the MTF analysis
                          (``"bullish"`` | ``"bearish"`` | ``"neutral"``).
    ``confirmed_count`` — number of factors where score > 0.
    ``total_factors``   — total factor count (8 when all inputs are valid).
    """
    model_config = ConfigDict(populate_by_name=True)

    pair:            str
    score:           int                        # 0–100
    bias:            str                        # "bullish" | "bearish" | "neutral"
    factors:         List[ConfluenceFactorOut]
    confirmed_count: int      = Field(alias="confirmedCount")
    total_factors:   int      = Field(alias="totalFactors")
    analysed_at:     Optional[datetime] = Field(default=None, alias="analysedAt")
