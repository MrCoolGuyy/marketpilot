"""
MarketPilot Models — Backtesting definitions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from marketpilot.core.enums import Interval
from marketpilot.models.strategy import SignalDirection


class BacktestTrade(BaseModel):
    """A log of a complete trade in historical simulation."""
    
    direction: SignalDirection = Field(description="LONG or SHORT")
    signal_time: datetime = Field(description="Time the signal triggered (candle close)")
    entry_time: datetime = Field(description="Time the position was opened (next candle open)")
    exit_time: datetime = Field(description="Time the position was closed")
    
    entry_price: Decimal = Field(description="Simulated fill price of entry")
    exit_price: Decimal = Field(description="Simulated fill price of exit")
    quantity: Decimal = Field(description="Base asset quantity")
    
    entry_fee: Decimal = Field(description="Fee paid on entry")
    exit_fee: Decimal = Field(description="Fee paid on exit")
    
    realized_pnl: Decimal = Field(description="Realized net PnL (including fees)")
    exit_reason: str = Field(description="Reason for exit (e.g. stop_loss, opposite_signal, end_of_data)")


class BacktestMetrics(BaseModel):
    """Key performance metrics of the backtest run."""
    
    starting_equity: Decimal = Field(description="Initial account equity")
    ending_equity: Decimal = Field(description="Final account equity")
    total_return_fraction: Decimal = Field(description="(ending_equity / starting_equity) - 1")
    max_drawdown_fraction: Decimal = Field(description="Max equity drop from peak")
    
    trade_count: int = Field(description="Total number of trades completed")
    win_rate: Optional[Decimal] = Field(description="Fraction of trades with positive PnL (None if no trades)")
    profit_factor: Optional[Decimal] = Field(description="Gross profit / Gross loss (None if zero losses)")


class BacktestResult(BaseModel):
    """Complete summary of a historical simulation run."""
    
    symbol: str = Field(description="Trading pair symbol")
    interval: Interval = Field(description="Candlestick timeframe")
    start_time: datetime = Field(description="Time of the very first evaluated candle")
    end_time: datetime = Field(description="Time of the last evaluated candle")
    
    trades: tuple[BacktestTrade, ...] = Field(description="All closed trades in chronological order")
    equity_curve: tuple[Decimal, ...] = Field(description="Account equity recorded before start, and at each closed candle")
    metrics: BacktestMetrics = Field(description="Calculated performance metrics")
