"""
MarketPilot Storage — SQLAlchemy ORM table definitions.

These models define the physical schema.  The ``Base`` declarative base
is shared across all tables and used by ``DatabaseManager`` for DDL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Kline storage
# ---------------------------------------------------------------------------

class KlineRecord(Base):
    """Persisted kline / candlestick data."""

    __tablename__ = "kline_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    high: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    low: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    close: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    volume: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    turnover: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_kline_symbol_interval_time", "symbol", "interval", "open_time", unique=True),
    )

    def __repr__(self) -> str:
        return f"<KlineRecord(symbol={self.symbol!r}, interval={self.interval!r}, open_time={self.open_time})>"


# ---------------------------------------------------------------------------
# Order log
# ---------------------------------------------------------------------------

class OrderRecord(Base):
    """Persisted order history."""

    __tablename__ = "order_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    order_link_id: Mapped[str] = mapped_column(String(64), default="")
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    qty: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    price: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), default="0")
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_order_symbol_status", "symbol", "status"),
    )

    def __repr__(self) -> str:
        return f"<OrderRecord(order_id={self.order_id!r}, symbol={self.symbol!r}, status={self.status!r})>"


# ---------------------------------------------------------------------------
# Trade log
# ---------------------------------------------------------------------------

class TradeRecord(Base):
    """Persisted public trades for analysis."""

    __tablename__ = "trade_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    price: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    quantity: Mapped[str] = mapped_column(Numeric(precision=20, scale=8, asdecimal=False), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        Index("ix_trade_symbol_time", "symbol", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<TradeRecord(trade_id={self.trade_id!r}, symbol={self.symbol!r})>"


# ---------------------------------------------------------------------------
# Paper Trading Storage
# ---------------------------------------------------------------------------

class PaperAccountRecord(Base):
    """Singleton-like table representing the paper trading account."""
    __tablename__ = "paper_accounts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    cash: Mapped[str] = mapped_column(String(32), nullable=False)
    locked_margin: Mapped[str] = mapped_column(String(32), nullable=False)
    realized_pnl: Mapped[str] = mapped_column(String(32), nullable=False)


class PaperPositionRecord(Base):
    """Active paper trading positions."""
    __tablename__ = "paper_positions"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_price: Mapped[str] = mapped_column(String(32), nullable=False)
    leverage: Mapped[int] = mapped_column(nullable=False)
    initial_margin: Mapped[str] = mapped_column(String(32), nullable=False)
    stop_loss: Mapped[str] = mapped_column(String(32), nullable=True)
    take_profit: Mapped[str] = mapped_column(String(32), nullable=True)
    entry_fee: Mapped[str] = mapped_column(String(32), nullable=False)


class PaperTradeRecord(Base):
    """Historical paper trades."""
    __tablename__ = "paper_trades"
    
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[str] = mapped_column(String(32), nullable=False)
    
    entry_price: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_fee: Mapped[str] = mapped_column(String(32), nullable=False)
    
    exit_price: Mapped[str] = mapped_column(String(32), nullable=True)
    exit_fee: Mapped[str] = mapped_column(String(32), nullable=True)
    exit_reason: Mapped[str] = mapped_column(String(32), nullable=True)
    
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    realized_pnl: Mapped[str] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
