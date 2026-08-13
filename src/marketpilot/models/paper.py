"""
MarketPilot Models — Paper Trading definitions.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from marketpilot.models.strategy import SignalDirection


class PaperPosition(BaseModel):
    """An open simulated position."""
    
    symbol: str = Field(description="Trading pair symbol")
    direction: SignalDirection = Field(description="LONG or SHORT")
    quantity: Decimal = Field(description="Base asset quantity")
    entry_price: Decimal = Field(description="Simulated fill price of entry")
    mark_price: Decimal = Field(description="Current market price for evaluation")
    leverage: int = Field(description="Leverage multiplier used")
    initial_margin: Decimal = Field(description="Quote asset held for margin")
    stop_loss: Optional[Decimal] = Field(default=None, description="Theoretical stop loss")
    take_profit: Optional[Decimal] = Field(default=None, description="Theoretical take profit")
    entry_fee: Decimal = Field(description="Fee paid on entry")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Mark-to-market PnL based on mark_price")


class PaperTrade(BaseModel):
    """A log of a simulated round-trip trade."""
    
    id: str = Field(description="Unique string identifier for the trade record")
    symbol: str = Field(description="Trading pair symbol")
    direction: SignalDirection = Field(description="LONG or SHORT")
    quantity: Decimal = Field(description="Base asset quantity")
    
    entry_price: Decimal = Field(description="Simulated fill price of entry")
    entry_fee: Decimal = Field(description="Fee paid on entry")
    
    exit_price: Optional[Decimal] = Field(default=None, description="Simulated fill price of exit")
    exit_fee: Optional[Decimal] = Field(default=None, description="Fee paid on exit")
    
    opened_at: datetime = Field(description="Time when the position was opened")
    closed_at: Optional[datetime] = Field(default=None, description="Time when the position was closed")
    
    realized_pnl: Optional[Decimal] = Field(default=None, description="Realized net PnL (including fees)")
    status: str = Field(description="OPEN or CLOSED")
    exit_reason: Optional[str] = Field(default=None, description="Reason for exit (e.g. stop_loss, take_profit, manual_close)")


class PaperAccountSnapshot(BaseModel):
    """State of the entire paper trading simulation."""
    
    cash: Decimal = Field(description="Available liquid cash (initial_equity + realized_pnl - locked_margin)")
    locked_margin: Decimal = Field(description="Total margin currently locked in positions")
    equity: Decimal = Field(description="Total account equity (cash + locked_margin + unrealized_pnl)")
    
    realized_pnl: Decimal = Field(description="Sum of all realized PnL across history")
    unrealized_pnl: Decimal = Field(description="Current unrealized PnL across all open positions")
    
    positions: tuple[PaperPosition, ...] = Field(description="All currently open positions")
    trades: tuple[PaperTrade, ...] = Field(description="All historical trades and currently open trades")
