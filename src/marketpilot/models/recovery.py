"""
MarketPilot Models - Recovery and state reconstruction models.
"""

from __future__ import annotations

from typing import Tuple, Optional
from pydantic import BaseModel, Field

class ReconciliationRecord(BaseModel):
    """A deeply immutable record of a state reconciliation."""
    model_config = {"frozen": True}
    record_id: str
    timestamp: float
    decision_id: Optional[str] = None
    issue_type: str
    resolution_action: str
    resolution_reason: Optional[str] = None

class ExchangeRecoverySnapshot(BaseModel):
    """An immutable snapshot of the exchange state used during recovery."""
    model_config = {"frozen": True}
    snapshot_id: str
    timestamp: float
    open_orders: Tuple[str, ...]
    active_positions: Tuple[str, ...]

class RecoveryResult(BaseModel):
    """The immutable result of the startup bidirectional lifecycle reconstruction."""
    model_config = {"frozen": True}
    success: bool
    snapshot: ExchangeRecoverySnapshot
    reconciled_records: Tuple[ReconciliationRecord, ...]
    fatal_error: Optional[str] = None
