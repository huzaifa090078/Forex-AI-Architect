"""
SQLAlchemy ORM models — one class per database table.
Alembic autogenerates migrations from these definitions.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ─── Users ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    trades: Mapped[List["Trade"]] = relationship("Trade", back_populates="user")
    signals: Mapped[List["Signal"]] = relationship("Signal", back_populates="user")
    backtests: Mapped[List["Backtest"]] = relationship("Backtest", back_populates="user")
    settings: Mapped[Optional["BotSettings"]] = relationship("BotSettings", back_populates="user", uselist=False)
    logs: Mapped[List["SystemLog"]] = relationship("SystemLog", back_populates="user")


# ─── Trades ──────────────────────────────────────────────────────────────────

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    signal_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("signals.id"), nullable=True)

    pair: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)   # "buy" | "sell"
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(Float, nullable=False)
    lot_size: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)

    pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_reward_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Broker reference
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="trades")
    signal: Mapped[Optional["Signal"]] = relationship("Signal", back_populates="trades")


# ─── Signals ─────────────────────────────────────────────────────────────────

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)

    pair: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    entry_zone_low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    entry_zone_high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_reward_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    smc_pattern: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    indicators: Mapped[List[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="signals")
    trades: Mapped[List["Trade"]] = relationship("Trade", back_populates="signal")


# ─── Backtests ───────────────────────────────────────────────────────────────

class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)

    strategy_id: Mapped[str] = mapped_column(String(100), nullable=False)
    pair: Mapped[str] = mapped_column(String(20), nullable=False)
    from_date: Mapped[str] = mapped_column(String(10), nullable=False)   # ISO date
    to_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)

    initial_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_balance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winning_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    losing_trades: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profit_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_pnl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sharpe_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    result_detail: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="backtests")


# ─── News Items ──────────────────────────────────────────────────────────────

class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    impact: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    actual: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    forecast: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    previous: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─── Bot Settings ─────────────────────────────────────────────────────────────

class BotSettings(Base):
    __tablename__ = "bot_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), unique=True, nullable=False)

    risk_per_trade: Mapped[float] = mapped_column(Float, default=1.0)
    max_open_trades: Mapped[int] = mapped_column(Integer, default=5)
    max_daily_loss: Mapped[float] = mapped_column(Float, default=5.0)
    allowed_pairs: Mapped[List[str]] = mapped_column(JSON, default=list)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    news_filter_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mt5_account: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mt5_server: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    min_confidence: Mapped[float] = mapped_column(Float, default=0.75)
    default_lot_size: Mapped[float] = mapped_column(Float, default=0.01)

    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="settings")


# ─── System Logs ─────────────────────────────────────────────────────────────

class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id"), nullable=True, index=True)

    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="logs")
