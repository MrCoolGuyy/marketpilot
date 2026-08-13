"""
MarketPilot Models - Risk domain models.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

class RiskDecision(BaseModel):
    """The outcome of evaluating a StrategyEvaluation through the Risk Engine."""
    
    approved: bool = Field(..., description="Whether the trade is approved to proceed")
    reason: str = Field(..., description="Explanation for approval or rejection")
    
    position_size: Decimal = Field(default=Decimal("0"), description="Approved position size in base coin (e.g. BTC qty)")
    risk_amount: Decimal = Field(default=Decimal("0"), description="Approved dollar amount at risk")
    
    # Final verified SL/TP
    sl: Decimal = Field(default=Decimal("0"), description="Verified Stop Loss price")
    tp: Decimal = Field(default=Decimal("0"), description="Verified Take Profit price")
    rr: Decimal = Field(default=Decimal("0"), description="Verified Reward-to-Risk ratio")
