"""
MarketPilot Models - Position domain models.

Defines the state machine and event sourcing types for PositionManager.
"""

from __future__ import annotations

from enum import Enum
from decimal import Decimal
from typing import Literal, Union
from pydantic import BaseModel, Field

class PositionStatus(str, Enum):
    """The explicit state machine statuses for a position."""
    NONE = "NONE"
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    TRAILING = "TRAILING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"

# --- Event Sourcing Events ---

class PositionEventBase(BaseModel, frozen=True):
    decision_id: str
    symbol: str
    timestamp: float

class PositionCreated(PositionEventBase):
    event_type: Literal["PositionCreated"] = "PositionCreated"
    qty: Decimal
    side: str

class EntryFilled(PositionEventBase):
    event_type: Literal["EntryFilled"] = "EntryFilled"
    fill_price: Decimal
    fill_qty: Decimal
    fee: Decimal

class TrailingMoved(PositionEventBase):
    event_type: Literal["TrailingMoved"] = "TrailingMoved"
    old_sl: Decimal
    new_sl: Decimal

class PartialClosed(PositionEventBase):
    event_type: Literal["PartialClosed"] = "PartialClosed"
    close_price: Decimal
    close_qty: Decimal
    realized_pnl: Decimal

class Exited(PositionEventBase):
    event_type: Literal["Exited"] = "Exited"
    exit_price: Decimal
    exit_qty: Decimal
    realized_pnl: Decimal
    reason: str

PositionEvent = Union[PositionCreated, EntryFilled, TrailingMoved, PartialClosed, Exited]
