"""
Centralised application settings loaded from environment variables.
All secrets must be provided via environment — never hard-coded.
"""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────────────────────
    APP_ENV: str = Field(default="development")
    APP_SECRET_KEY: str = Field(...)
    APP_DEBUG: bool = Field(default=False)
    APP_HOST: str = Field(default="0.0.0.0")
    APP_PORT: int = Field(default=8000)
    ALLOWED_ORIGINS: List[str] = Field(default=["http://localhost:5173"])

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(...)

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def ensure_asyncpg_scheme(cls, v: str) -> str:
        """Convert postgresql:// → postgresql+asyncpg:// and strip params
        asyncpg doesn't accept (e.g. sslmode)."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        # Strip query params unsupported by asyncpg driver
        if "?" in v:
            from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
            parsed = urlparse(v)
            params = parse_qs(parsed.query, keep_blank_values=True)
            # asyncpg handles SSL natively; drop driver-incompatible params
            for key in ("sslmode", "sslcert", "sslkey", "sslrootcert"):
                params.pop(key, None)
            new_query = urlencode({k: v[0] for k, v in params.items()})
            v = urlunparse(parsed._replace(query=new_query))
        return v
    DATABASE_POOL_SIZE: int = Field(default=10)
    DATABASE_MAX_OVERFLOW: int = Field(default=20)

    # ── JWT / Auth ────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(...)
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)

    # ── MT5 / Exness ─────────────────────────────────────────────────────────
    MT5_ACCOUNT: int = Field(default=0)
    MT5_PASSWORD: str = Field(default="")
    MT5_SERVER: str = Field(default="")
    MT5_TERMINAL_PATH: str = Field(default="")
    # Maximum number of reconnect attempts after a mid-session MT5 disconnect.
    MT5_RECONNECT_ATTEMPTS: int = Field(default=5)
    # Base delay (seconds) for the first reconnect attempt; doubles each retry.
    MT5_RECONNECT_DELAY_SECONDS: float = Field(default=2.0)

    # ── AI Engine (ML scaffold — future use) ─────────────────────────────────
    AI_MODEL_PATH: str = Field(default="./models")
    AI_MIN_CONFIDENCE: float = Field(default=0.75)
    AI_INFERENCE_DEVICE: str = Field(default="cpu")

    # ── AI Engine (rule-based decision engine) ────────────────────────────────
    # Maximum spread in pips before the engine rejects a setup as NO_TRADE.
    # Mirrors the scanner's internal _MAX_SPREAD_PIPS = 3.0 constant.
    AI_MAX_SPREAD_PIPS: float = Field(default=3.0)
    # When True, High-volatility setups (ATR% > 0.10) are penalised and rejected.
    AI_VOLATILITY_FILTER_ENABLED: bool = Field(default=False)
    # Session names the engine considers tradeable. Empty list = all sessions.
    AI_TRADEABLE_SESSIONS: List[str] = Field(default=[])

    # ── Market Data ──────────────────────────────────────────────────────────
    MARKET_SCAN_INTERVAL_SECONDS: int = Field(default=60)
    # How often (seconds) the live feed polls tick data for all pairs.
    MARKET_TICK_INTERVAL_SECONDS: int = Field(default=5)

    # ── News Filter ──────────────────────────────────────────────────────────
    NEWS_API_KEY: str = Field(default="")
    NEWS_FILTER_ENABLED: bool = Field(default=True)
    NEWS_HIGH_IMPACT_BLOCK_MINUTES: int = Field(default=30)

    # ── Risk Management ──────────────────────────────────────────────────────
    # (Section 8 — RuleBasedRiskManager)
    RISK_PER_TRADE_PERCENT: float = Field(default=1.0)
    MAX_OPEN_TRADES: int = Field(default=5)
    MAX_DAILY_LOSS_PERCENT: float = Field(default=5.0)
    DEFAULT_LOT_SIZE: float = Field(default=0.01)

    # Minimum reward:risk ratio required for trade approval (e.g. 2.0 = 1:2)
    RISK_MIN_RR: float = Field(default=2.0)

    # Optional daily profit target; 0.0 = disabled (default).
    # When enabled and reached, new trades are blocked for the remainder of the day.
    RISK_MAX_DAILY_PROFIT_PERCENT: float = Field(default=0.0)

    # Maximum allowable drawdown from the day-open equity (%).
    RISK_MAX_DRAWDOWN_PERCENT: float = Field(default=10.0)

    # Number of consecutive losing trades that triggers a trading block.
    RISK_MAX_CONSECUTIVE_LOSSES: int = Field(default=3)

    # Maximum spread in pips allowed by the Risk Manager (independent of AI engine limit).
    RISK_MAX_SPREAD_PIPS: float = Field(default=3.0)

    # Maximum stop-loss distance in pips; 0.0 = unlimited.
    RISK_MAX_SL_PIPS: float = Field(default=0.0)

    # Allowed trading sessions for the Risk Manager.
    # Empty list = all sessions permitted.  Values: "London", "New York",
    # "London/NY Overlap", "Asian", "Off Hours".
    RISK_ALLOWED_SESSIONS: List[str] = Field(default=[])

    # Maximum total open lots across all positions before new trades are blocked.
    RISK_MAX_TOTAL_OPEN_LOTS: float = Field(default=5.0)

    # Maximum lots allocated to a single currency (base or quote) across all positions.
    RISK_MAX_CURRENCY_EXPOSURE_LOTS: float = Field(default=2.0)

    # ── Backtesting ──────────────────────────────────────────────────────────
    BACKTEST_DATA_PATH: str = Field(default="./data/historical")
    BACKTEST_WORKERS: int = Field(default=4)

    # ── Logging ──────────────────────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="json")
    LOG_FILE: str = Field(default="./logs/forex_bot.log")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
