"""
MarketPilot Strategy - Portfolio Policy.

Defines the immutable versioned bounds for portfolio admission.
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional

class PortfolioPolicy(BaseModel, frozen=True):
    """
    Explicit, versioned constraints for portfolio capital admission.
    Phase-5 purely evaluates against these rules.
    """
    policy_version: str = Field(..., description="Deterministic version hash or semantic version")

    allocated_capital: Optional[Decimal] = Field(
        default=None, description="Explicitly allocated risk capital for MarketPilot."
    )
    minimum_unallocated_buffer: Decimal = Field(
        default=Decimal("3.0"),
        description="Minimum cash buffer that must remain unallocated in the account.",
    )

    # Heat limits
    max_total_heat_ratio: Decimal = Field(
        default=Decimal("0.10"),
        description="Maximum sum of (risk/equity) across all active and pending reservations."
    )

    # Lineage limits
    max_simultaneous_lineages: int = Field(
        default=1,
        description="Maximum active logical lineages allowed globally."
    )

    def calculate_effective_risk_capital(self, usable_account_value: Decimal) -> Decimal:
        if self.allocated_capital is None:
            return Decimal("0")
        capital_after_buffer = max(usable_account_value - self.minimum_unallocated_buffer, Decimal("0"))
        return min(self.allocated_capital, capital_after_buffer)
