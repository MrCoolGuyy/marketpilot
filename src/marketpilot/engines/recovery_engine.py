"""
MarketPilot Engines - Recovery Engine.

Recovers PositionManager state from the Exchange on daemon boot.
Resolves conflicts deterministically and emits RecoveryConflict exceptions if unresolvable.
"""

from __future__ import annotations

import time
from decimal import Decimal
from loguru import logger

from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.engines.position_manager import PositionManager, PositionStatus
from marketpilot.models.position import PositionCreated, EntryFilled

class RecoveryConflict(Exception):
    """Raised when local state and exchange state contradict each other and cannot be safely resolved."""
    pass

class RecoveryEngine:
    """Rebuilds state from the exchange."""
    
    def __init__(self, client: BybitClient, position_manager: PositionManager):
        self._client = client
        self._pm = position_manager

    async def run_recovery(self):
        """Fetches active positions and orders, rebuilding the position manager."""
        logger.info("Running deterministic state recovery...")
        
        # 1. Fetch Exchange Snapshot
        pos_resp = await self._client.get_positions()
        raw_positions = pos_resp.get("result", {}).get("list", [])
        
        active_exchange_positions = {}
        for p in raw_positions:
            size = Decimal(p.get("size", "0"))
            if size > Decimal("0"):
                active_exchange_positions[p["symbol"]] = p
                
        # 2. Compare and Resolve
        # For daemon boot, our local PositionManager is likely empty, so we hydrate entirely from exchange.
        # But if there were pending local states, we would compare them.
        
        for symbol, p in active_exchange_positions.items():
            local_pos = self._pm.get_position(symbol)
            size = Decimal(p.get("size", "0"))
            entry_price = Decimal(p.get("avgPrice", "0"))
            side = p.get("side", "None")
            
            if local_pos is None:
                # Hydrate from scratch
                logger.info(f"Hydrating {symbol} from Exchange: Qty {size} at {entry_price}")
                
                now = time.time()
                # Create fake initial events to bootstrap the state machine
                self._pm.process_event(PositionCreated(
                    decision_id="recovery-boot",
                    symbol=symbol,
                    timestamp=now,
                    qty=size,
                    side=side
                ))
                self._pm.process_event(EntryFilled(
                    decision_id="recovery-boot",
                    symbol=symbol,
                    timestamp=now + 0.1,
                    fill_price=entry_price,
                    fill_qty=size,
                    fee=Decimal("0") # Unknown past fee
                ))
            else:
                # Compare sizes
                if local_pos.qty != size:
                    raise RecoveryConflict(
                        f"State mismatch on {symbol}: Local Qty {local_pos.qty}, Exchange Qty {size}"
                    )
                if local_pos.status not in (PositionStatus.OPEN, PositionStatus.PARTIAL, PositionStatus.TRAILING):
                    raise RecoveryConflict(
                        f"State mismatch on {symbol}: Local Status {local_pos.status.name} but Exchange says OPEN"
                    )
                    
        # 3. Verify
        # If local PM has an OPEN position that exchange does not have, emit conflict.
        for symbol, local_pos in list(self._pm.positions.items()):
            if local_pos.status in (PositionStatus.OPEN, PositionStatus.PARTIAL, PositionStatus.TRAILING):
                if symbol not in active_exchange_positions:
                    raise RecoveryConflict(
                        f"State mismatch on {symbol}: Local claims OPEN, but Exchange has NO POSITION."
                    )
                    
        logger.info("Recovery completed successfully. State is synchronized.")
