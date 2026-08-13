"""
MarketPilot Models - Strategy Registry domain models.
"""

from __future__ import annotations

from enum import Enum
from typing import Tuple, Optional
from pydantic import BaseModel

class PromotionStatus(str, Enum):
    """The status of a strategy in the registry."""
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    RETIRED = "RETIRED"

class StrategyRegistryEntry(BaseModel):
    """An immutable entry representing a versioned strategy implementation and parameter set."""
    model_config = {"frozen": True}
    strategy_id: str
    strategy_version: str
    parameter_set_id: str
    promotion_status: PromotionStatus
    evidence_references: Tuple[str, ...]

class RegistrySnapshot(BaseModel):
    """An immutable snapshot of the strategy registry for exact-version validation."""
    model_config = {"frozen": True}
    registry_version: str
    entries: Tuple[StrategyRegistryEntry, ...]
