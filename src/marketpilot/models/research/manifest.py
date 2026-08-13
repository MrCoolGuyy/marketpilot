"""
MarketPilot Research - Manifest Model.

Immutable record of a research cycle for reproducibility.
"""

from pydantic import BaseModel
from typing import Optional

class ResearchManifest(BaseModel, frozen=True):
    """Metadata tracking a specific run of the Research Engine."""
    analytics_version: str
    dataset_hash: str
    config_hash: str
    git_commit: Optional[str] = None
    python_version: str
    
    created_time: float
    trade_count: int
    feature_count: int
