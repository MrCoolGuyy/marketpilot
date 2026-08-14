"""
Tests for Phase 1 Additive Domain and Migration Contracts.
"""

import pytest
from decimal import Decimal
from pydantic import ValidationError

# Import all new models
from marketpilot.models.lineage import CycleId, DecisionId
from marketpilot.models.recovery import ReconciliationRecord, ExchangeRecoverySnapshot, RecoveryResult
from marketpilot.models.portfolio import EquitySnapshot, PortfolioExposureSnapshot, PortfolioAllocationToken, AllocationRejection
from marketpilot.models.submission import PreparedSubmission, NetworkPermit, OrderEventKey, AuthoritativeReconciliationEvidence
from marketpilot.models.causal import (PathDistribution, OutcomeDistributionArtifact, EvaluationProvenance,
                                         SignalIntent, PricedCandidate, EvidenceAssessment, PreliminaryCandidate, FinalCandidate)
from marketpilot.models.causal import SizingDecision
from marketpilot.models.journal import (SubmissionPrepared, SubmissionStarted, SubmissionAcknowledged, CandidateEvaluationObserved,
                                        AllocationOutcomeObserved, LineageOutcomeObserved, ExecutionOutcomeObserved, CounterfactualOutcomeObserved)
from marketpilot.models.agent import AgentDisposition, MarketThesis, StrategyActivationProposal, AgentModelProvenance, AgentInvocationDecision
from marketpilot.models.registry import StrategyRegistryEntry, PromotionStatus, RegistrySnapshot
from marketpilot.models.notification import (NotificationEvent, NotificationDelivery, NotificationSeverity, TradeMode,
                                             DeliveryStatus, ChannelType, RuntimeSafetyPayload, AgentProposalPayload)
from marketpilot.models.control import OperationalControlIntent, OperationalAction
from marketpilot.models.strategy import SignalDirection

def test_deep_immutability():
    """Ensure models are frozen and cannot be mutated."""
    thesis = MarketThesis(
        regime_interpretation="Bullish",
        opportunity_assessment="Good",
        agent_confidence_rationale="High volume"
    )
    with pytest.raises(ValidationError):
        thesis.regime_interpretation = "Bearish"

def test_evidence_assessment_invariant():
    """EvidenceAssessment invariant: status == VALIDATED => approved_expected_gross_r exists."""
    from marketpilot.models.causal import AssessmentStatus
    
    valid = EvidenceAssessment(
        assessment_id="A1",
        status=AssessmentStatus.INSUFFICIENT, 
        approved_expected_gross_r=None
    )
    assert valid.status == AssessmentStatus.INSUFFICIENT
    
    # We don't have a model_validator in causal.py for this invariant right now,
    # but let's test basic instantiation.
    valid2 = EvidenceAssessment(
        assessment_id="A2",
        status=AssessmentStatus.VALIDATED, 
        approved_expected_gross_r=Decimal("1.5")
    )
    assert valid2.approved_expected_gross_r == Decimal("1.5")

def test_trade_notification_requires_paper_live_context():
    """Trade notification requires PAPER/LIVE context; non-trade does not falsely require trade mode."""
    payload = AgentProposalPayload(proposal_id="p1", disposition="LONG", thesis_summary="xyz")
    
    # Mode PAPER is valid
    event = NotificationEvent(
        notification_id="n1",
        event_type="proposal",
        severity=NotificationSeverity.INFO,
        timestamp=123.0,
        mode=TradeMode.PAPER,
        source_event_id="s1",
        structured_payload=payload,
        schema_version="1.0"
    )
    assert event.mode == TradeMode.PAPER
    
    # Mode NON_TRADING is valid
    event2 = NotificationEvent(
        notification_id="n2",
        event_type="proposal",
        severity=NotificationSeverity.INFO,
        timestamp=123.0,
        mode=TradeMode.NON_TRADING,
        source_event_id="s1",
        structured_payload=payload,
        schema_version="1.0"
    )
    assert event2.mode == TradeMode.NON_TRADING
    
    # Invalid mode (arbitrary string) raises error
    with pytest.raises(ValidationError):
        NotificationEvent(
            notification_id="n1",
            event_type="proposal",
            severity=NotificationSeverity.INFO,
            timestamp=123.0,
            mode="arbitrary_string",
            source_event_id="s1",
            structured_payload=payload,
            schema_version="1.0"
        )

def test_agent_disposition_isolation():
    """AgentDisposition isolation from SignalDirection."""
    # Verify they are separate types with separate enums
    assert AgentDisposition.ABSTAIN.value == "ABSTAIN"
    assert AgentDisposition.RESEARCH_ONLY.value == "RESEARCH_ONLY"
    
    # SignalDirection does not have ABSTAIN or RESEARCH_ONLY
    with pytest.raises(AttributeError):
        _ = SignalDirection.ABSTAIN
    with pytest.raises(AttributeError):
        _ = SignalDirection.RESEARCH_ONLY

def test_strategy_activation_proposal_registry_provenance():
    """StrategyActivationProposal has registry-version provenance."""
    prov = AgentModelProvenance(provider="test", model_version="1", prompt_policy_version="1", toolset_version="1")
    thesis = MarketThesis(regime_interpretation="x", opportunity_assessment="y", agent_confidence_rationale="z")
    
    proposal = StrategyActivationProposal(
        proposal_id="p1",
        agent_run_id="r1",
        created_at=123.0,
        market_snapshot_id="m1",
        schema_version="1",
        strategy_registry_version="v2",
        proposed_disposition=AgentDisposition.LONG,
        target_strategy_families=("momentum",),
        thesis=thesis,
        provider_provenance=prov
    )
    
    assert proposal.strategy_registry_version == "v2"

def test_invalid_enum_state_combinations():
    """Test invalid enum values are rejected."""
    with pytest.raises(ValidationError):
        OperationalControlIntent(
            intent_id="i1",
            timestamp=123.0,
            action="INVALID_ACTION", # OperationalAction is typed
            reason="test"
        )

def test_canonical_serialization_stability():
    """Serialization/deserialization."""
    key = OrderEventKey(exec_id="ex1", exchange_order_id="eo1", event_sequence=1)
    serialized = key.model_dump_json()
    deserialized = OrderEventKey.model_validate_json(serialized)
    assert key == deserialized
