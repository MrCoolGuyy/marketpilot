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
    snapshot_id: str
    version: str
    captured_at: float
    environment: str
    safe_account_fingerprint: str
    configured_allocated_capital: Optional[Decimal]
    usable_account_value: Decimal
    effective_risk_capital: Decimal
    freshness_status: str
    provenance: str

class PortfolioExposureSnapshot(BaseModel):
    """Immutable snapshot of the exposure manager's state."""
    model_config = {"frozen": True}
    exposure_version: str
    timestamp: float
    active_position_ids: Tuple[str, ...]
    reserved_allocation_ids: Tuple[str, ...]
    active_risk_amount: Decimal = Field(default=Decimal("0"))
    reserved_risk_amount: Decimal = Field(default=Decimal("0"))

    # Context injected by ExposureManager for observability
    policy_limit_risk_amount: Decimal = Field(default=Decimal("0"))
    policy_max_lineages: int = Field(default=0)

    @property
    def total_risk_amount(self) -> Decimal:
        """Derived invariant: total_risk_amount = active + reserved"""
        return self.active_risk_amount + self.reserved_risk_amount

class PortfolioAllocationToken(BaseModel):
    """Immutable allocator-approved trade intent and provenance."""
    model_config = {"frozen": True}

    candidate_id: str
    decision_id: str

    strategy_id: str
    strategy_version: str
    parameter_set_id: str
    symbol: str
    direction: str

    sizing_id: str
    effective_stop: Decimal
    quantity: Decimal
    executable_entry: Decimal
    candidate_risk_amount: Decimal
    final_net_ev: Decimal

    portfolio_snapshot_version: str
    equity_snapshot_version: str
    portfolio_policy_version: str

    reservation_identity: str
    lineage_identity: str
    admission_timestamp: float

class AllocationRejection(BaseModel):
    """Typed rejection reason for portfolio allocation failure."""
    model_config = {"frozen": True}
    decision_id: str
    rejection_code: str
    reason: str

class PortfolioAdmissionDecision(BaseModel):
    """Envelope returning either Admitted (with Token) or Rejected."""
    model_config = {"frozen": True}
    decision_id: str
    is_admitted: bool
    rejection: Optional[AllocationRejection] = None
    token: Optional[PortfolioAllocationToken] = None

    @property
    def is_rejected(self) -> bool:
        return not self.is_admitted
