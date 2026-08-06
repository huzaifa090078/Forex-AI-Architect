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
    risk_reward_ratio: Optional[float] = None
    notes: Optional[str] = None
    signal_id: Optional[str] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime


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


# ─── News ─────────────────────────────────────────────────────────────────────

class NewsItemOut(BaseModel):
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
