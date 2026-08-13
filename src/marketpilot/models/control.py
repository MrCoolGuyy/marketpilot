"""
MarketPilot Models - Operational Control Intent.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel

class OperationalAction(str, Enum):
    """Explicitly sanctioned human operational control actions."""
    PAUSE_TRADING = "PAUSE_TRADING"
    RESUME_TRADING = "RESUME_TRADING"
    REQUEST_CLOSE_POSITION = "REQUEST_CLOSE_POSITION"
    DISABLE_NEW_ENTRIES = "DISABLE_NEW_ENTRIES"
    EMERGENCY_HALT = "EMERGENCY_HALT"

class OperationalControlIntent(BaseModel):
    """Immutable intent for an explicitly sanctioned human control request."""
    model_config = {"frozen": True}
    intent_id: str
    timestamp: float
    action: OperationalAction
    target_symbol: str | None = None
    target_trade_id: str | None = None
    reason: str
