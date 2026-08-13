"""
MarketPilot Models - Portfolio domain models.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Tuple, Optional
from pydantic import BaseModel, Field

class PortfolioSnapshot(BaseModel, frozen=True):
    """Snapshot of the account portfolio at a specific point in time."""
    timestamp: float
    
    equity: Decimal = Field(..., description="Total account equity")
    balance: Decimal = Field(..., description="Wallet balance")
    margin_used: Decimal = Field(..., description="Total margin used by open positions")
    
    drawdown_percent: Decimal = Field(default=Decimal("0"), description="Current drawdown from peak")
    exposure_percent: Decimal = Field(default=Decimal("0"), description="Percentage of equity currently at risk")
    
    open_risk: Decimal = Field(default=Decimal("0"), description="Total dollar amount at risk across all stops")

class EquitySnapshot(BaseModel):
    """Immutable batch snapshot of account equity."""
    model_config = {"frozen": True}
    snapshot_version: str
    timestamp: float
    total_equity: Decimal
    available_balance: Decimal

class PortfolioExposureSnapshot(BaseModel):
    """Immutable snapshot of the exposure manager's state."""
    model_config = {"frozen": True}
    exposure_version: str
    timestamp: float
    active_position_ids: Tuple[str, ...]
    reserved_allocation_ids: Tuple[str, ...]
    total_heat: Decimal

class PortfolioAllocationToken(BaseModel):
    """Immutable allocator-approved trade intent and provenance."""
    model_config = {"frozen": True}
    allocation_id: str
    decision_id: str
    symbol: str
    side: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    provisional_quantity: Decimal
    approved_risk: Decimal
    ev_provenance_id: str
    intent_fingerprint: str
    exposure_snapshot_version: str
    equity_snapshot_version: str
    portfolio_policy_version: str
    cluster_map_version: str
    resolved_cluster_ids: Tuple[str, ...]

class AllocationRejection(BaseModel):
    """Typed rejection reason for portfolio allocation failure."""
    model_config = {"frozen": True}
    decision_id: str
    rejection_code: str
    reason: str
