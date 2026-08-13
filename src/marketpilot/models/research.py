"""MarketPilot Models — Research Journal."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from marketpilot.models.strategy import SignalDirection

class ResearchOutcome(str, Enum):
    """Possible outcomes for a captured research observation."""
    OPEN = "OPEN"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    INVALID = "INVALID"

class ResearchObservation(BaseModel):
    """A captured snapshot of a strategy signal for out-of-sample forward evaluation."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str = Field(description="Trading pair symbol")
    interval: str = Field(description="Kline interval used (e.g. 60)")
    signal_time: datetime = Field(description="The open time of the candle where the signal was finalized")
    capture_time: datetime = Field(description="When this observation was saved locally")
    
    direction: SignalDirection = Field(description="Direction of the signal")
    entry_price: Decimal = Field(description="The exact price simulated at entry (close of signal candle)")
    stop_loss: Decimal = Field(description="Evaluated stop loss")
    take_profit: Decimal = Field(description="Evaluated take profit")
    theoretical_quantity: Decimal = Field(description="Position size given theoretical equity")
    
    strategy_settings: dict[str, Any] = Field(description="Snapshot of strategy config")
    risk_settings: dict[str, Any] = Field(description="Snapshot of risk config")
    
    status: ResearchOutcome = Field(default=ResearchOutcome.OPEN)
    resolved_time: Optional[datetime] = Field(default=None, description="When the status was resolved (time of the candle)")
    resolved_price: Optional[Decimal] = Field(default=None, description="The price that triggered the outcome")
    realized_r: Optional[Decimal] = Field(default=None, description="R-multiple captured (-1 for SL, >0 for TP)")

class ResearchReport(BaseModel):
    """Aggregated statistics of evaluated observations."""
    total_observations: int
    resolved_count: int
    open_count: int
    
    win_rate: Optional[Decimal] = None
    average_r: Optional[Decimal] = None
    expectancy: Optional[Decimal] = None
    max_drawdown_r: Optional[Decimal] = None
    
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
