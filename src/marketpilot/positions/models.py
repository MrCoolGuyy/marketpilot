"""Position manager models."""

from enum import Enum
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional

class PositionAction(str, Enum):
    """Actions the manager can propose."""
    HOLD = "HOLD"
    CLOSE_STOP_LOSS = "CLOSE_STOP_LOSS"
    CLOSE_TAKE_PROFIT = "CLOSE_TAKE_PROFIT"
    INVALID = "INVALID"

class PositionDecision(BaseModel):
    """Immutable evaluation decision for a position."""
    symbol: str = Field(description="Trading pair symbol")
    action: PositionAction = Field(description="Proposed action")
    mark_price: Optional[Decimal] = Field(description="The price used for evaluation")
    reason: str = Field(description="Human-readable reason for the decision")
