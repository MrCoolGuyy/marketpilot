"""
MarketPilot Models - Trade domain models.
"""

from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, Field

from marketpilot.models.strategy import SignalDirection
from marketpilot.models.regime import MarketRegime

class TradePlan(BaseModel):
    """A fully verified, unified plan ready for validation and execution."""
    
    decision_id: str = Field(..., description="UUID tracing this decision pipeline tick")
    symbol: str = Field(..., description="Trading pair, e.g. 'BTCUSDT'")
    direction: SignalDirection = Field(..., description="Trade direction (LONG or SHORT)")
    
    # Execution targets
    entry: Decimal = Field(..., description="Planned entry price")
    sl: Decimal = Field(..., description="Planned stop loss price")
    tp: Decimal = Field(..., description="Planned take profit price")
    qty: Decimal = Field(..., description="Calculated position size (base coin)")
    risk: Decimal = Field(..., description="Calculated risk amount (quote coin)")
    expected_rr: Decimal = Field(..., description="Reward-to-Risk ratio")
    
    # Context (for journaling and dashboard)
    strategy: str = Field(..., description="Name of the strategy that generated the signal")
    confidence: Decimal = Field(..., description="Confidence score of the strategy (0-100)")
    market_regime: MarketRegime = Field(..., description="Current market regime")
    market_quality: Decimal = Field(..., description="Market quality score (0-100) from Scanner")
    reason: str = Field(..., description="Explanation of why this trade was planned")
    
    timestamp: float = Field(..., description="Unix timestamp of plan creation")
