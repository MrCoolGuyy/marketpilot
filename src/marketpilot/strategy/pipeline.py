"""
MarketPilot Strategy - Causal Pipeline.

Ties together all Phase 4 sealed components:
SignalIntent -> Pricing -> Validation -> Economics -> Re-Ranking
"""

from typing import Sequence

from pydantic import BaseModel
from marketpilot.models.causal import (
    SignalIntent, 
    ExecutableQuoteSnapshot, 
    FinalCandidate,
    CandidateEvaluationObserved,
    CandidateRejectedObserved,
    CounterfactualCandidateObserved
)
from marketpilot.strategy.pricing_policy import PricingPolicy
from marketpilot.strategy.validation_policy import ValidationPolicy
from marketpilot.strategy.economics import CausalEconomicsEngine

class EvaluationBatchResult(BaseModel):
    """Immutable batch outcome from the causal pipeline."""
    candidates: list[FinalCandidate]
    observations: list[CandidateEvaluationObserved | CandidateRejectedObserved | CounterfactualCandidateObserved]

class CausalPipeline:
    """Executes the Phase 4 pipeline for a batch of SignalIntents."""
    
    def __init__(
        self, 
        pricing: PricingPolicy, 
        validation: ValidationPolicy, 
        economics: CausalEconomicsEngine
    ):
        self.pricing = pricing
        self.validation = validation
        self.economics = economics
        
    def process_signals(
        self, 
        intents: Sequence[SignalIntent], 
        quotes: dict[str, ExecutableQuoteSnapshot],
        regime_model: str,
        regime_state: str,
        market_scope: str
    ) -> EvaluationBatchResult:
        """
        Process intents through the pipeline and return ranked candidates and observations.
        """
        import uuid
        candidates = []
        observations = []
        
        for intent in intents:
            # 1. Pricing
            quote = quotes.get(intent.identity.strategy_id)
            if not quote:
                from marketpilot.core.enums import PricingStatus, AssessmentStatus
                obs = CandidateRejectedObserved(
                    observation_id=str(uuid.uuid4()),
                    intent_id=intent.intent_id,
                    snapshot_id=intent.provenance_snapshot_id,
                    symbol=intent.symbol,
                    identity=intent.identity,
                    direction=intent.direction,
                    signal_timestamp=intent.signal_timestamp,
                    quote_id=None,
                    quote_timestamp=None,
                    evidence_status=AssessmentStatus.INAPPLICABLE,
                    pricing_status=PricingStatus.UNPRICEABLE,
                    rejection_reason="No executable quote available for strategy"
                )
                observations.append(obs)
                continue
                
            priced = self.pricing.price_intent(intent, quote)
            if priced.rejection_reason:
                from marketpilot.core.enums import AssessmentStatus
                obs = CandidateRejectedObserved(
                    observation_id=str(uuid.uuid4()),
                    intent_id=intent.intent_id,
                    snapshot_id=intent.provenance_snapshot_id,
                    symbol=intent.symbol,
                    identity=intent.identity,
                    direction=intent.direction,
                    signal_timestamp=intent.signal_timestamp,
                    quote_id=quote.quote_id,
                    quote_timestamp=quote.quote_timestamp,
                    evidence_status=AssessmentStatus.INAPPLICABLE,
                    pricing_status=priced.pricing_status,
                    executable_entry_price=priced.executable_entry_price if hasattr(priced, "executable_entry_price") else None,
                    rejection_reason=priced.rejection_reason
                )
                observations.append(obs)
                continue
                 
            # 2. Validation
            assessment = self.validation.assess(priced, regime_model, regime_state, market_scope)
            if assessment.rejection_reason:
                obs = CandidateRejectedObserved(
                    observation_id=str(uuid.uuid4()),
                    intent_id=intent.intent_id,
                    snapshot_id=intent.provenance_snapshot_id,
                    symbol=intent.symbol,
                    identity=intent.identity,
                    direction=intent.direction,
                    signal_timestamp=intent.signal_timestamp,
                    quote_id=quote.quote_id,
                    quote_timestamp=quote.quote_timestamp,
                    evidence_status=assessment.status,
                    pricing_status=priced.pricing_status,
                    executable_entry_price=priced.executable_entry_price if hasattr(priced, "executable_entry_price") else None,
                    rejection_reason=assessment.rejection_reason
                )
                observations.append(obs)
                continue
            
            # 3. Pre-size Economics
            pre_size = self.economics.evaluate_pre_size(priced, assessment)
            
            # 4. Sizing
            sizing = self.economics.provisional_size(priced)
            
            # 5. Size-Aware Economics
            size_aware = self.economics.evaluate_size_aware(priced, pre_size, sizing)
            
            # 6. Build Candidate
            final = self.economics.build_final_candidate(priced, assessment, pre_size, sizing, size_aware)
            
            if final.rejection_reason:
                obs = CandidateRejectedObserved(
                    observation_id=str(uuid.uuid4()),
                    intent_id=intent.intent_id,
                    snapshot_id=intent.provenance_snapshot_id,
                    symbol=intent.symbol,
                    identity=intent.identity,
                    direction=intent.direction,
                    signal_timestamp=intent.signal_timestamp,
                    quote_id=final.priced_candidate.quote.quote_id if final.priced_candidate.quote else None,
                    quote_timestamp=final.priced_candidate.quote.quote_timestamp if final.priced_candidate.quote else None,
                    evidence_status=final.assessment.status,
                    pricing_status=final.priced_candidate.pricing_status,
                    executable_entry_price=final.priced_candidate.executable_entry_price if hasattr(final.priced_candidate, "executable_entry_price") else None,
                    rejection_reason=final.rejection_reason
                )
                observations.append(obs)
            else:
                candidates.append(final)
            
        # 7. Global Re-Rank
        # FinalNetEV_R DESC -> signal_timestamp ASC -> deterministic_decision_key ASC
        candidates.sort(
            key=lambda c: (
                -c.size_aware_economics.final_net_ev_r,
                c.priced_candidate.intent.signal_timestamp,
                c.deterministic_decision_key
            )
        )
        
        # Build evaluation observations for ranked candidates
        for i, final in enumerate(candidates):
            rank = i + 1
            obs = CandidateEvaluationObserved(
                observation_id=str(uuid.uuid4()),
                candidate_id=final.candidate_id,
                snapshot_id=final.priced_candidate.intent.provenance_snapshot_id,
                identity=final.priced_candidate.intent.identity,
                direction=final.priced_candidate.intent.direction,
                signal_timestamp=final.priced_candidate.intent.signal_timestamp,
                evidence_status=final.assessment.status,
                pre_size_net_ev_r=final.pre_size_economics.pre_size_net_ev_r,
                provisional_quantity=final.sizing.provisional_quantity,
                final_net_ev_r=final.size_aware_economics.final_net_ev_r,
                deterministic_decision_key=final.deterministic_decision_key,
                rank=rank
            )
            observations.append(obs)
            
            # We can also emit Counterfactual candidate for the top N, let's say all for now
            cf = CounterfactualCandidateObserved(
                observation_id=str(uuid.uuid4()),
                candidate=final,
                rank=rank
            )
            observations.append(cf)
        
        return EvaluationBatchResult(
            candidates=candidates,
            observations=observations
        )
