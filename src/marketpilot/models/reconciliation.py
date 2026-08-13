"""
MarketPilot Models - Reconciliation domain models.
"""

from __future__ import annotations

from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, Field
from marketpilot.models.trade import TradePlan
from marketpilot.models.execution import ExecutionResult

class ReconciliationReport(BaseModel, frozen=True):
    """The result of reconciling a TradePlan against an ExecutionResult."""
    decision_id: str
    
    expected_entry: Decimal
    executed_entry: Decimal
    slippage_bps: Decimal = Field(..., description="Slippage in basis points")
    
    expected_qty: Decimal
    executed_qty: Decimal
    qty_mismatch: bool
    
    expected_fee: Decimal = Field(default=Decimal("0"))
    actual_fee: Decimal = Field(default=Decimal("0"))
    is_maker: bool = Field(default=False)
    
    realized_spread: Decimal = Field(default=Decimal("0"))
    
    warnings: list[str] = Field(default_factory=list)
