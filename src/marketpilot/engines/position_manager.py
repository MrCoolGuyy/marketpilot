"""
MarketPilot Engines - Position Manager.

Manages open position state machine transitions via event sourcing.
"""

from __future__ import annotations

from typing import Optional
from decimal import Decimal

from marketpilot.models.position import (
    PositionStatus,
    PositionEvent,
    PositionCreated,
    EntryFilled,
    TrailingMoved,
    PartialClosed,
    Exited
)

class PositionState:
    """The current state of a position, hydrated from events."""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.status: PositionStatus = PositionStatus.NONE
        self.qty = Decimal("0")
        self.entry_price = Decimal("0")
        self.sl = Decimal("0")
        self.realized_pnl = Decimal("0")
        self.events: list[PositionEvent] = []

    def apply_event(self, event: PositionEvent):
        """Reduces an event into the current state."""
        self.events.append(event)
        
        if isinstance(event, PositionCreated):
            if self.status != PositionStatus.NONE:
                raise ValueError(f"Invalid transition: Cannot create position from state {self.status.name}")
            self.qty = event.qty
            self.status = PositionStatus.PENDING_ENTRY
            
        elif isinstance(event, EntryFilled):
            if self.status != PositionStatus.PENDING_ENTRY:
                raise ValueError(f"Invalid transition: Cannot fill entry from state {self.status.name}")
            self.entry_price = event.fill_price
            self.qty = event.fill_qty # Final confirmed qty
            self.status = PositionStatus.OPEN
            
        elif isinstance(event, TrailingMoved):
            if self.status not in (PositionStatus.OPEN, PositionStatus.PARTIAL, PositionStatus.TRAILING):
                raise ValueError(f"Invalid transition: Cannot move trailing SL from state {self.status.name}")
            self.sl = event.new_sl
            self.status = PositionStatus.TRAILING
            
        elif isinstance(event, PartialClosed):
            if self.status not in (PositionStatus.OPEN, PositionStatus.PARTIAL, PositionStatus.TRAILING):
                raise ValueError(f"Invalid transition: Cannot partial close from state {self.status.name}")
            self.qty -= event.close_qty
            self.realized_pnl += event.realized_pnl
            self.status = PositionStatus.PARTIAL
            if self.qty <= Decimal("0"):
                self.status = PositionStatus.CLOSED
                
        elif isinstance(event, Exited):
            if self.status == PositionStatus.CLOSED:
                raise ValueError("Position already closed.")
            self.qty = Decimal("0")
            self.realized_pnl += event.realized_pnl
            self.status = PositionStatus.CLOSED

class PositionManager:
    """Manages all active position state machines."""
    
    def __init__(self):
        self.positions: dict[str, PositionState] = {}
        
    def get_position(self, symbol: str) -> Optional[PositionState]:
        return self.positions.get(symbol)
        
    def process_event(self, event: PositionEvent) -> None:
        symbol = event.symbol
        if symbol not in self.positions:
            if isinstance(event, PositionCreated):
                self.positions[symbol] = PositionState(symbol)
            else:
                raise ValueError(f"Received event {type(event).__name__} for unknown position {symbol}")
                
        pos = self.positions[symbol]
        pos.apply_event(event)
        
        # Cleanup closed positions (or keep them in memory for analytics)
        # For memory safety, we'll keep them but usually we'd flush to disk
