"""
MarketPilot Strategy - Portfolio Policy.

Defines the immutable versioned bounds for portfolio admission.
"""

from pydantic import BaseModel, Field
from decimal import Decimal

class PortfolioPolicy(BaseModel, frozen=True):
    """
    Explicit, versioned constraints for portfolio capital admission.
    Phase-5 purely evaluates against these rules.
    """
    policy_version: str = Field(..., description="Deterministic version hash or semantic version")

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
