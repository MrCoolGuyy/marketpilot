"""
MarketPilot Strategy - Validation Policy.

Evaluates an EvidenceApplicability against available StrategyEvidence
to produce a deterministic EvidenceAssessment.
"""

from typing import Optional
import time
import uuid
from decimal import Decimal

from marketpilot.models.causal import (
    EvidenceApplicability, 
    StrategyEvidence, 
    EvidenceAssessment, 
    AssessmentStatus,
    PricedCandidate
)

class ValidationPolicy:
    """Validates if current evidence is sufficient for execution."""
    
    def __init__(self, evidence_repository: list[StrategyEvidence]):
        self._evidence = evidence_repository
        
    def assess(self, candidate: PricedCandidate, current_regime_model: str, current_regime_state: str, market_scope: str) -> EvidenceAssessment:
        """
        Assess if the PricedCandidate has sufficient validated evidence.
        """
        intent = candidate.intent
        identity = intent.identity
        
        # In a real system, we'd query the DB. Here we scan our injected repository.
        matching_evidence = None
        has_any_evidence = False
        
        for ev in self._evidence:
            app = ev.applicability
            if (app.strategy_id == identity.strategy_id and
                app.strategy_version == identity.strategy_version and
                app.parameter_set_id == identity.parameter_set_id):
                
                has_any_evidence = True
                
                if (app.direction == intent.direction and
                    app.regime_model == current_regime_model and
                    app.regime_state == current_regime_state and
                    app.market_scope == market_scope):
                    
                    matching_evidence = ev
                    break
                
        if not matching_evidence:
            if not has_any_evidence:
                return EvidenceAssessment(
                    assessment_id=str(uuid.uuid4()),
                    status=AssessmentStatus.NO_EVIDENCE,
                    rejection_reason="No evidence artifact exists for this strategy identity"
                )
            else:
                return EvidenceAssessment(
                    assessment_id=str(uuid.uuid4()),
                    status=AssessmentStatus.INAPPLICABLE,
                    rejection_reason="Evidence artifact exists but applicability dimensions do not match current state"
                )
            
        # Check staleness: if research cutoff is older than 30 days compared to signal timestamp
        if matching_evidence.applicability.research_cutoff_timestamp < (intent.signal_timestamp - 86400 * 30):
             return EvidenceAssessment(
                assessment_id=str(uuid.uuid4()),
                status=AssessmentStatus.STALE,
                rejection_reason="Evidence is older than 30 days"
            )
            
        # Check insufficiency: Example policy requires ExpectedGrossR > 0.1
        expected_gross_r = matching_evidence.distribution.expected_gross_r
        if expected_gross_r < Decimal("0.1"):
             return EvidenceAssessment(
                assessment_id=str(uuid.uuid4()),
                status=AssessmentStatus.INSUFFICIENT,
                rejection_reason=f"ExpectedGrossR ({expected_gross_r}) below minimum policy threshold (0.1)"
            )
            
        # Accept evidence
        return EvidenceAssessment(
            assessment_id=str(uuid.uuid4()),
            status=AssessmentStatus.VALIDATED,
            approved_expected_gross_r=expected_gross_r,
            evidence_id=matching_evidence.evidence_id
        )
