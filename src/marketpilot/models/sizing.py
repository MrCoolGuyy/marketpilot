"""
MarketPilot Models - Sizing and Risk contracts.
"""

from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel

class SizingDecision(BaseModel):
    """Immutable record of the risk engine's position sizing decision."""
    model_config = {"frozen": True}
    decision_id: str
    allocation_id: str
    symbol: str
    sized_quantity: Decimal
    risk_amount: Decimal
    risk_policy_version: str
