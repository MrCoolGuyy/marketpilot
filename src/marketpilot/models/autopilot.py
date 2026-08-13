"""MarketPilot Models — Autopilot."""

from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from marketpilot.core.enums import Interval
from marketpilot.models.strategy import SignalDirection


class AutopilotStatus(str, Enum):
    """Execution status for a candidate."""
    DISARMED = "DISARMED"
    SUGGEST_ONLY = "SUGGEST_ONLY"
    ARMED_DEMO = "ARMED_DEMO"
    REJECTED = "REJECTED"
    KILLED = "KILLED"
    SUBMITTED = "SUBMITTED"


class CandidateDecision(BaseModel):
    """Immutable record of an autopilot execution decision."""

    symbol: str
    interval: Interval
    candle_time: datetime
    direction: SignalDirection
    score: Decimal
    turnover: Decimal
    
    entry_estimate: Decimal
    quantity: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    
    status: AutopilotStatus
    reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

    model_config = {"frozen": True}
