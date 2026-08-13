"""
MarketPilot Models - Strategy Evidence and Evaluation Pipeline models.
"""

from __future__ import annotations

from typing import Tuple, Optional
from decimal import Decimal
from pydantic import BaseModel, model_validator

from marketpilot.models.strategy import SignalDirection

class PathDistribution(BaseModel):
    """Empirical probability and expectancy for a specific exit path."""
    model_config = {"frozen": True}
    path_name: str
    probability: Decimal
    expected_r: Decimal

class OutcomeDistributionArtifact(BaseModel):
    """Versioned empirical outcome distribution artifact."""
    model_config = {"frozen": True}
    artifact_id: str
    strategy_id: str
    version: str
    expected_gross_r: Decimal
    path_distributions: Tuple[PathDistribution, ...]

class EvaluationProvenance(BaseModel):
    """Deeply immutable provenance for strategy evaluation."""
    model_config = {"frozen": True}
    cycle_id: str
    decision_id: str
    evidence_artifact_id: str
    validation_policy_version: str
    execution_cost_model_version: str
    pricing_policy_version: str

class SignalIntent(BaseModel):
    """Initial causal signal output by a strategy."""
    model_config = {"frozen": True}
    strategy_id: str
    direction: SignalDirection
    signal_timestamp: float

class PricedCandidate(BaseModel):
    """Signal intent priced according to the PricingPolicy."""
    model_config = {"frozen": True}
    intent: SignalIntent
    proposed_entry: Decimal
    proposed_sl: Decimal
    proposed_tp: Decimal

class EvidenceAssessment(BaseModel):
    """The result of validating empirical evidence."""
    model_config = {"frozen": True}
    live_eligible: bool
    approved_expected_gross_r: Optional[Decimal] = None
    outcome_artifact: Optional[OutcomeDistributionArtifact] = None

    @model_validator(mode="after")
    def validate_eligibility(self) -> EvidenceAssessment:
        if self.live_eligible and self.approved_expected_gross_r is None:
            raise ValueError("live_eligible requires approved_expected_gross_r to be set")
        return self

class PreliminaryCandidate(BaseModel):
    """Candidate after pre-size EV calculation."""
    model_config = {"frozen": True}
    priced: PricedCandidate
    assessment: EvidenceAssessment
    pre_size_net_ev_r: Decimal
    provenance: EvaluationProvenance

class FinalCandidate(BaseModel):
    """The fully sized candidate with finalized execution cost and Net EV."""
    model_config = {"frozen": True}
    preliminary: PreliminaryCandidate
    sized_quantity: Decimal
    size_dependent_cost_r: Decimal
    final_net_ev_r: Decimal
    deterministic_decision_key: str
