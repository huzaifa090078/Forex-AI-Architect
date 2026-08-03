"""
Centralised application settings loaded from environment variables.
All secrets must be provided via environment — never hard-coded.
"""

from functools import lru_cache
from typing import List

from pydantic import Field
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

    # ── AI Engine ────────────────────────────────────────────────────────────
    AI_MODEL_PATH: str = Field(default="./models")
    AI_MIN_CONFIDENCE: float = Field(default=0.75)
    AI_INFERENCE_DEVICE: str = Field(default="cpu")

    # ── Market Data ──────────────────────────────────────────────────────────
    MARKET_DATA_PROVIDER: str = Field(default="mt5")
    ALPHA_VANTAGE_API_KEY: str = Field(default="")
    MARKET_SCAN_INTERVAL_SECONDS: int = Field(default=60)

    # ── News Filter ──────────────────────────────────────────────────────────
    NEWS_API_KEY: str = Field(default="")
    NEWS_FILTER_ENABLED: bool = Field(default=True)
    NEWS_HIGH_IMPACT_BLOCK_MINUTES: int = Field(default=30)

    # ── Risk Management ──────────────────────────────────────────────────────
    RISK_PER_TRADE_PERCENT: float = Field(default=1.0)
    MAX_OPEN_TRADES: int = Field(default=5)
    MAX_DAILY_LOSS_PERCENT: float = Field(default=5.0)
    DEFAULT_LOT_SIZE: float = Field(default=0.01)

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
