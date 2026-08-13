"""
MarketPilot Models - Strategy domain models.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SignalDirection(str, Enum):
    """Direction of the trading signal."""
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class StrategyEvaluation(BaseModel):
    """The explicit trade parameters proposed by a strategy."""
    
    expected_win_rate: Decimal = Field(..., description="Estimated probability of winning (0-100)")
    
    # Risk/Reward explicit parameters
    entry_price: Decimal = Field(..., description="Proposed entry price")
    stop_loss: Decimal = Field(..., description="Proposed stop loss price")
    take_profit: Decimal = Field(..., description="Proposed take profit price")
    expected_rr: Decimal = Field(..., description="Expected reward-to-risk ratio")


class StrategyResult(BaseModel, frozen=True):
    """The immutable outcome of evaluating a single strategy."""
    
    strategy_name: str = Field(..., description="Name of the strategy")
    signal: SignalDirection = Field(..., description="Proposed trade direction (or HOLD)")
    
    confidence: Decimal = Field(default=Decimal("0"), description="Confidence score (0-100)")
    reason_code: str = Field(..., description="Short deterministic reason for the decision")
    
    metrics: dict[str, str] = Field(default_factory=dict, description="Internal variables at evaluation time")
    
    candidate_trade: Optional[StrategyEvaluation] = Field(
        default=None, 
        description="Populated only if signal is LONG or SHORT"
    )

    @property
    def is_actionable(self) -> bool:
        """Helper to determine if this result proposes a new trade."""
        return self.signal in (SignalDirection.LONG, SignalDirection.SHORT) and self.candidate_trade is not None
