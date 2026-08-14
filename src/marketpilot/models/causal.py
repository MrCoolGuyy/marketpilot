"""
MarketPilot Models - Causal Strategy and Statistical Pipeline Models.

Phase 4 immutable models that enforce causal boundaries, exact identity resolution,
price-free signals, and deterministic expectancy/economics validation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from enum import StrEnum
from pydantic import BaseModel, Field

from marketpilot.core.enums import Interval, MarketDataEnvironment, OrderSide

# ==============================================================================
# 1. CAUSAL MARKET FACTS
# ==============================================================================

class MarketFacts(BaseModel, frozen=True):
    """Deterministic market features used downstream. Missing values are None, not fabricated."""
    
    # OHLCV (Base)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal
    
    # Required computed features
    spread_bps: Decimal
    atr_percent: Decimal
    momentum_24h: Decimal
    trend_strength: Decimal
    trend_age_candles: int
    
    # Optional explicitly available features (OPTIONAL_PHASE4)
    funding_rate: Optional[Decimal] = Field(default=None, description="OPTIONAL_PHASE4")
    open_interest: Optional[Decimal] = Field(default=None, description="OPTIONAL_PHASE4")
    market_quality_score: Optional[Decimal] = Field(default=None, description="OPTIONAL_PHASE4")


class ClosedInstrumentSnapshot(BaseModel, frozen=True):
    """
    Immutable representation of exactly one causally closed market state.
    Must never contain forming candles or future data.
    """
    snapshot_id: str = Field(..., description="Unique ID for this exact market state")
    snapshot_version: str = Field(default="1.0")
    
    symbol: str
    interval: Interval
    environment: MarketDataEnvironment
    
    # Causal Timestamps
    candle_open_time: float
    candle_close_time: float = Field(..., description="Exact timestamp the boundary candle closed")
    creation_timestamp: float = Field(..., description="When this snapshot was finalized")
    
    feature_set_version: str = Field(..., description="Identity of the feature calculation logic")
    
    facts: MarketFacts = Field(..., description="Canonical facts derived strictly before creation_timestamp")


class SnapshotBuildOutcome(StrEnum):
    """Structured outcomes for snapshot building."""
    BUILT = "BUILT"
    NO_CLOSED_CANDLES = "NO_CLOSED_CANDLES"
    INSUFFICIENT_CLOSED_HISTORY = "INSUFFICIENT_CLOSED_HISTORY"
    NON_MONOTONIC_HISTORY = "NON_MONOTONIC_HISTORY"
    INVALID_INTERVAL = "INVALID_INTERVAL"
    INVALID_CAUSAL_BOUNDARY = "INVALID_CAUSAL_BOUNDARY"


class SnapshotBuildResult(BaseModel, frozen=True):
    """Typed result of the finalization process."""
    outcome: SnapshotBuildOutcome
    snapshot: Optional[ClosedInstrumentSnapshot] = None
    reason: Optional[str] = None


# ==============================================================================
# 2. STRATEGY REGISTRY & SIGNAL INTENT
# ==============================================================================

class SignalDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    HOLD = "HOLD"


class StrategyIdentity(BaseModel, frozen=True):
    """Exact identity binding for a strategy evaluation."""
    registry_version: str
    strategy_id: str
    strategy_version: str
    parameter_set_id: str


class SignalIntent(BaseModel, frozen=True):
    """
    Causally generated trade intent.
    STRICTLY PRICE-FREE: No historical entry price may be attached here.
    """
    intent_id: str
    identity: StrategyIdentity
    direction: SignalDirection
    symbol: str = Field(..., description="The instrument symbol for this intent")
    
    signal_timestamp: float = Field(..., description="When the signal was generated")
    
    # Logic boundaries (stop/target) defined conceptually (e.g. percentages, absolute price logic computed from facts)
    # In V1 we represent these as explicit prices *only* if derived purely from the closed facts (e.g. ATR bands).
    # They do NOT imply a fill price.
    logical_stop_loss: Decimal
    logical_take_profit: Decimal
    
    provenance_snapshot_id: str = Field(..., description="ClosedInstrumentSnapshot ID that generated this signal")


# ==============================================================================
# 3. EXECUTABLE QUOTE & CAUSAL PRICING
# ==============================================================================

class PricingStatus(StrEnum):
    PRICED = "PRICED"
    UNPRICEABLE = "UNPRICEABLE"


class ExecutableQuoteSnapshot(BaseModel, frozen=True):
    """The first realistically observable executable market state after a signal."""
    quote_id: str
    symbol: str
    environment: MarketDataEnvironment
    
    # Must be >= signal_timestamp
    quote_timestamp: float
    
    bid: Decimal
    ask: Decimal
    # Optional liquidity depths
    bid_qty_available: Optional[Decimal] = None
    ask_qty_available: Optional[Decimal] = None


class PricedCandidate(BaseModel, frozen=True):
    """A SignalIntent successfully priced against a real ExecutableQuoteSnapshot."""
    candidate_id: str
    intent: SignalIntent
    quote: ExecutableQuoteSnapshot
    
    pricing_status: PricingStatus
    executable_entry_price: Decimal
    
    rejection_reason: Optional[str] = None


# ==============================================================================
# 4. EVIDENCE & VALIDATION POLICY
# ==============================================================================

class EvidenceApplicability(BaseModel, frozen=True):
    """Explicit dimension binding to prove evidence applies to the current state."""
    strategy_id: str
    strategy_version: str
    parameter_set_id: str
    timeframe: Interval
    direction: SignalDirection
    
    regime_model: str
    regime_state: str
    
    market_scope: str
    execution_policy_version: str
    research_cutoff_timestamp: float


class OutcomeObservation(BaseModel, frozen=True):
    realized_r: Decimal

class OutcomeDistributionArtifact(BaseModel, frozen=True):
    """Immutable full-outcome distribution statistics for ExpectedGrossR."""
    artifact_id: str
    outcomes: tuple[OutcomeObservation, ...] = Field(..., min_length=1)
    
    @property
    def expected_gross_r(self) -> Decimal:
        """Deterministically derived arithmetic mean of realized_r."""
        total = sum((o.realized_r for o in self.outcomes), Decimal("0"))
        return total / Decimal(len(self.outcomes))


class StrategyEvidence(BaseModel, frozen=True):
    evidence_id: str
    applicability: EvidenceApplicability
    distribution: OutcomeDistributionArtifact


class AssessmentStatus(StrEnum):
    VALIDATED = "VALIDATED"
    INSUFFICIENT = "INSUFFICIENT"
    STALE = "STALE"
    INAPPLICABLE = "INAPPLICABLE"
    NO_EVIDENCE = "NO_EVIDENCE"


class EvidenceAssessment(BaseModel, frozen=True):
    """Immutable validation policy outcome."""
    assessment_id: str
    status: AssessmentStatus
    approved_expected_gross_r: Optional[Decimal] = None
    rejection_reason: Optional[str] = None
    
    evidence_id: Optional[str] = None


# ==============================================================================
# 5. ECONOMICS & SIZING
# ==============================================================================

class PreSizeEconomics(BaseModel, frozen=True):
    """Scale-linear costs known before quantity-dependent impact."""
    approved_expected_gross_r: Decimal
    pre_size_expected_cost_r: Decimal
    pre_size_net_ev_r: Decimal
    cost_model_provenance: str


class SizingDecision(BaseModel, frozen=True):
    """Deterministic provisional sizing from RiskEngine."""
    sizing_id: str
    provisional_quantity: Decimal
    risk_policy_provenance: str


class SizeAwareEconomics(BaseModel, frozen=True):
    """Quantity-dependent execution economics."""
    size_aware_cost_r: Decimal
    final_net_ev_r: Decimal


class FinalCandidate(BaseModel, frozen=True):
    """The globally ranked economic candidate ready for Phase 5."""
    candidate_id: str
    priced_candidate: PricedCandidate
    assessment: EvidenceAssessment
    pre_size_economics: PreSizeEconomics
    sizing: SizingDecision
    size_aware_economics: SizeAwareEconomics
    
    is_eligible: bool
    rejection_reason: Optional[str] = None
    
    # Final Ranking Deterministic Key
    @property
    def deterministic_decision_key(self) -> str:
        ident = self.priced_candidate.intent.identity
        sym = self.priced_candidate.intent.symbol
        return f"{sym}:{ident.strategy_id}:{ident.strategy_version}:{ident.parameter_set_id}:{self.priced_candidate.intent.direction.value}"


# ==============================================================================
# 6. EVALUATION OBSERVATIONS
# ==============================================================================

class CandidateEvaluationObserved(BaseModel, frozen=True):
    """Immutable record of a successfully evaluated candidate."""
    observation_id: str
    candidate_id: str
    snapshot_id: str
    identity: StrategyIdentity
    direction: SignalDirection
    signal_timestamp: float
    evidence_status: AssessmentStatus
    pre_size_net_ev_r: Decimal
    provisional_quantity: Decimal
    final_net_ev_r: Decimal
    deterministic_decision_key: str
    rank: int


class CandidateRejectedObserved(BaseModel, frozen=True):
    """Immutable record of a candidate rejected during evaluation."""
    observation_id: str
    intent_id: str
    snapshot_id: str
    symbol: str
    identity: StrategyIdentity
    direction: SignalDirection
    signal_timestamp: float
    quote_id: Optional[str] = None
    quote_timestamp: Optional[float] = None
    evidence_status: AssessmentStatus
    pricing_status: PricingStatus
    executable_entry_price: Optional[Decimal] = None
    rejection_reason: str


class CounterfactualCandidateObserved(BaseModel, frozen=True):
    """Immutable record of an evaluated candidate selected for counterfactual tracking."""
    observation_id: str
    candidate: FinalCandidate
    rank: int

# ==============================================================================
# PHASE 1 COMPATIBILITY RE-EXPORTS / TYPES
# ==============================================================================

class PathDistribution(BaseModel, frozen=True):
    path_name: str
    probability: Decimal
    expected_r: Decimal

class EvaluationProvenance(BaseModel, frozen=True):
    cycle_id: str
    decision_id: str
    evidence_artifact_id: str
    validation_policy_version: str
    execution_cost_model_version: str
    pricing_policy_version: str

class PreliminaryCandidate(BaseModel, frozen=True):
    priced: PricedCandidate
    assessment: EvidenceAssessment
    pre_size_net_ev_r: Decimal
    provenance: EvaluationProvenance
