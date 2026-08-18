"""
MarketPilot Engines - Recovery Engine.

Recovers PositionManager state from the Exchange on daemon boot.
Resolves conflicts deterministically and emits RecoveryConflict exceptions if unresolvable.
"""

from __future__ import annotations

import time
from decimal import Decimal
from loguru import logger

import json
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.engines.position_manager import PositionManager, PositionStatus
from marketpilot.engines.exposure_manager import ExposureManager
from marketpilot.engines.journal_engine import JournalEngine
from marketpilot.models.position import PositionCreated, EntryFilled
from pydantic import BaseModel, Field

class RecoveryConflict(Exception):
    """Raised when local state and exchange state contradict each other and cannot be safely resolved."""
    pass

class RecoveryResult(BaseModel):
    is_safe: bool
    reasons: list[str] = Field(default_factory=list)

class RecoveryEngine:
    """Rebuilds state from the exchange and journal."""

    def __init__(
        self,
        client: BybitClient,
        position_manager: PositionManager,
        exposure_manager: ExposureManager = None,
        journal_engine: JournalEngine = None
    ):
        self._client = client
        self._pm = position_manager
        self._em = exposure_manager or ExposureManager()
        self._je = journal_engine or JournalEngine()

    async def run_recovery(self) -> RecoveryResult:
        """Fetches active positions and orders, rebuilding the position manager and exposure manager."""
        logger.info("Running deterministic state recovery...")

        reasons = []
        is_safe = True

        # 1. Fetch Exchange Snapshot
        try:
            pos_resp = await self._client.get_positions()
            raw_positions = pos_resp.get("result", {}).get("list", [])
        except Exception as e:
            return RecoveryResult(is_safe=False, reasons=[f"Failed to fetch exchange positions: {e}"])

        active_exchange_positions = {}
        for p in raw_positions:
            size = Decimal(p.get("size", "0"))
            if size > Decimal("0"):
                active_exchange_positions[p["symbol"]] = p

        # 2. Compare and Resolve PositionManager
        for symbol, p in active_exchange_positions.items():
            local_pos = self._pm.get_position(symbol)
            size = Decimal(p.get("size", "0"))
            entry_price = Decimal(p.get("avgPrice", "0"))
            side = p.get("side", "None")

            if local_pos is None:
                # Hydrate from scratch
                logger.info(f"Hydrating {symbol} from Exchange: Qty {size} at {entry_price}")
                now = time.time()
                self._pm.process_event(PositionCreated(
                    decision_id="recovery-boot", symbol=symbol, timestamp=now, qty=size, side=side
                ))
                self._pm.process_event(EntryFilled(
                    decision_id="recovery-boot", symbol=symbol, timestamp=now + 0.1, fill_price=entry_price, fill_qty=size, fee=Decimal("0")
                ))
            else:
                if local_pos.qty != size:
                    is_safe = False
                    reasons.append(f"State mismatch on {symbol}: Local Qty {local_pos.qty}, Exchange Qty {size}")
                if local_pos.status not in (PositionStatus.OPEN, PositionStatus.PARTIAL, PositionStatus.TRAILING):
                    is_safe = False
                    reasons.append(f"State mismatch on {symbol}: Local Status {local_pos.status.name} but Exchange says OPEN")

        for symbol, local_pos in list(self._pm.positions.items()):
            if local_pos.status in (PositionStatus.OPEN, PositionStatus.PARTIAL, PositionStatus.TRAILING):
                if symbol not in active_exchange_positions:
                    is_safe = False
                    reasons.append(f"State mismatch on {symbol}: Local claims OPEN, but Exchange has NO POSITION.")

        # 3. Rehydrate ExposureManager from Journal Phase-5 Events
        committed_allocations = {} # allocation_id -> risk_amount
        aborted_allocations = set()

        if self._je.events_path.exists():
            with open(self._je.events_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip(): continue
                    try:
                        record = json.loads(line)
                        event_type = record.get("type", "")
                        alloc_id = record.get("allocation_id")

                        if event_type == "AllocationCommitted" and alloc_id:
                            committed_allocations[alloc_id] = Decimal(str(record.get("risk_amount", "0")))
                        elif event_type == "ReservationAborted" and alloc_id:
                            aborted_allocations.add(alloc_id)
                    except Exception:
                        pass

        active_risk = Decimal("0")
        reserved_risk = Decimal("0")
        reserved_ids = []

        for alloc_id, risk in committed_allocations.items():
            if alloc_id in aborted_allocations:
                continue

            symbol = alloc_id.split(":")[0]
            if symbol in active_exchange_positions:
                active_risk += risk
            else:
                reserved_ids.append(alloc_id)
                reserved_risk += risk

        # Validate that all active exchange positions have a corresponding committed lineage
        # Only active exchange positions that were successfully parsed get evaluated
        for symbol in active_exchange_positions:
            matched = any(a.startswith(f"{symbol}:") for a in committed_allocations if a not in aborted_allocations)
            if not matched:
                is_safe = False
                reasons.append(f"Exchange has active position for {symbol} but no committed lineage exists in Journal. STATE_MISMATCH.")

        if is_safe:
            self._em.replace_all(
                active_position_ids=list(active_exchange_positions.keys()),
                active_risk_amount=active_risk,
                reserved_allocation_ids=reserved_ids,
                reserved_risk_amount=reserved_risk
            )
            logger.info(f"Recovery safely rehydrated. Active Risk: {active_risk}, Reserved Risk: {reserved_risk}")
        else:
            logger.error(f"Recovery unsafe: {reasons}")

        return RecoveryResult(is_safe=is_safe, reasons=reasons)
