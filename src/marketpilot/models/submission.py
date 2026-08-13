"""
MarketPilot Models - Submission and network permit models.
"""

from __future__ import annotations

from typing import Tuple
from pydantic import BaseModel, Field

class NetworkPermit(BaseModel):
    """Structurally proves a durable SUBMISSION_STARTED has been safely written."""
    model_config = {"frozen": True}
    permit_id: str
    allocation_id: str
    client_order_id: str

class AuthoritativeReconciliationEvidence(BaseModel):
    """Evidence consumed to resolve ambiguous lifecycle states."""
    model_config = {"frozen": True}
    evidence_id: str
    source_type: str # REST, WS, MANUAL
    exchange_order_id: str
    status: str
    filled_qty: str
    avg_price: str

class OrderEventKey(BaseModel):
    """Durable typed event fingerprint for order updates."""
    model_config = {"frozen": True}
    exec_id: str
    exchange_order_id: str
    event_sequence: int

class PreparedSubmission(BaseModel):
    """The fully prepared payload ready for submission, bounded by risk quantization."""
    model_config = {"frozen": True}
    submission_id: str
    allocation_id: str
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    qty: str
    price: str
    stop_loss: str
    take_profit: str
