"""
MarketPilot Dashboard - Read Models for Phase 4.

Strictly read-only projections of the canonical state.
"""

from pydantic import BaseModel
from typing import Optional, Generic, TypeVar
from decimal import Decimal

T = TypeVar('T')

class ProjectionMetadata(BaseModel):
    schema_version: str = "1.0"
    projection_version: int
    evaluation_id: str
    daemon_instance_id: str
    generated_at: float
    evaluation_as_of: float
    cycle_outcome: str = "UNKNOWN"
    cycle_reason: Optional[str] = None
    
    # Attrition metrics
    intents_count: int = 0
    priced_count: int = 0
    evidence_evaluated_count: int = 0
    final_candidates_count: int = 0
    rejected_before_pricing_count: int = 0
    rejected_at_evidence_count: int = 0
    rejected_at_economics_count: int = 0
    
    # Compatibility with tests
    candidates_count: int = 0
    
    evaluation_cadence_seconds: int = 60

class ProjectionEnvelope(BaseModel, Generic[T]):
    metadata: ProjectionMetadata
    data: T

class DaemonLifecycleProjection(BaseModel):
    daemon_instance_id: str
    status: str = "UNKNOWN"
    mode: str = "CONTINUOUS"
    started_at: float
    heartbeat_at: float
    completed_at: Optional[float] = None

# ==============================================================================
# MARKET INTELLIGENCE
# ==============================================================================

class MarketIntelligenceReadModel(BaseModel):
    snapshot_id: str
    snapshot_version: str
    symbol: str
    timeframe: str
    market_data_environment: str
    
    # Causal bounds
    candle_open_timestamp: float
    candle_close_timestamp: float
    snapshot_creation_timestamp: float
    
    # Facts (Required)
    open: str
    high: str
    low: str
    close: str
    volume: str
    turnover: str
    
    spread_bps: str
    atr_percent: str
    momentum_24h: str
    trend_strength: str
    trend_age_candles: int
    
    # Optional explicitly available features
    funding_rate: Optional[str] = None
    open_interest: Optional[str] = None
    market_quality_score: Optional[str] = None


# ==============================================================================
# EVIDENCE TRACEABILITY
# ==============================================================================

class EvidenceTraceabilityReadModel(BaseModel):
    """Exposes a candidate read model containing enough provenance to trace the pipeline."""
    
    # FACT
    snapshot_id: str
    symbol: str  # ADDED
    signal_timestamp: float
    quote_id: Optional[str] = None
    quote_timestamp: Optional[float] = None
    
    # STRATEGY OUTPUT
    strategy_id: str
    strategy_version: str
    parameter_set_id: str
    direction: str
    logical_stop_loss: Optional[str] = None
    logical_take_profit: Optional[str] = None
    
    # CORE VALIDATION / ECONOMICS
    pricing_status: str
    executable_entry_price: Optional[str] = None
    
    evidence_status: str
    approved_expected_gross_r: Optional[str] = None
    
    pre_size_expected_cost_r: Optional[str] = None
    pre_size_net_ev_r: Optional[str] = None
    
    sizing_id: Optional[str] = None
    provisional_quantity: Optional[str] = None
    
    size_aware_cost_r: Optional[str] = None
    final_net_ev_r: Optional[str] = None
    
    is_eligible: bool
    rejection_reason: Optional[str] = None
    deterministic_rank: Optional[int] = None
    deterministic_decision_key: Optional[str] = None
