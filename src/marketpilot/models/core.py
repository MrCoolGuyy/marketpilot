"""
MarketPilot Models - Core shared models.
"""

from pydantic import BaseModel, Field

class EngineMetadata(BaseModel):
    """Metadata output for engine observability."""
    decision_id: str = Field(default="", description="UUID tracing this specific decision pipeline tick")
    processing_time_ms: float = Field(default=0.0)
    version: str = Field(default="1.0.0")
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
