"""
MarketPilot Models - Lineage and identity types.
"""

from __future__ import annotations

from typing import NewType

CycleId = NewType("CycleId", str)
DecisionId = NewType("DecisionId", str)
AllocationId = NewType("AllocationId", str)
TradeId = NewType("TradeId", str)
MutationId = NewType("MutationId", str)
ClientOrderId = NewType("ClientOrderId", str)
