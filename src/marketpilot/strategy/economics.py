"""
MarketPilot Strategy - Economics & Sizing.

Calculates pre-size and size-aware economics, and produces SizingDecisions.
"""

from decimal import Decimal
import uuid
from typing import Optional

from marketpilot.models.causal import (
    PricedCandidate,
    EvidenceAssessment,
    PreSizeEconomics,
    SizingDecision,
    SizeAwareEconomics,
    FinalCandidate
)

class CausalEconomicsEngine:
    """Computes deterministic costs and sizing."""
    
    def __init__(self, taker_fee_rate: Decimal = Decimal("0.00055"), account_equity: Decimal = Decimal("1000")):
        self.taker_fee_rate = taker_fee_rate
        self.account_equity = account_equity
        # For simplicity, risk 1% of equity per trade
        self.risk_fraction = Decimal("0.01")
        
    def evaluate_pre_size(self, candidate: PricedCandidate, assessment: EvidenceAssessment) -> PreSizeEconomics:
        """Computes scale-linear costs (e.g. basic spread and fee slippage) assuming R=1."""
        if not assessment.approved_expected_gross_r:
            return PreSizeEconomics(
                approved_expected_gross_r=Decimal("0"),
                pre_size_expected_cost_r=Decimal("0"),
                pre_size_net_ev_r=Decimal("0"),
                cost_model_provenance="None"
            )
            
        gross_r = assessment.approved_expected_gross_r
        
        # Simple cost model: assume 1 R unit is degraded by fees.
        # This is a stub for Phase 4. We deduct a flat R penalty for fees and spread.
        # Example: fees cost 0.1 R
        cost_r = Decimal("0.10") 
        
        return PreSizeEconomics(
            approved_expected_gross_r=gross_r,
            pre_size_expected_cost_r=cost_r,
            pre_size_net_ev_r=gross_r - cost_r,
            cost_model_provenance="v1.0-linear"
        )
        
    def provisional_size(self, candidate: PricedCandidate) -> SizingDecision:
        """Determines provisional quantity before checking liquidity impact."""
        intent = candidate.intent
        
        # Risk amount in quote
        risk_amount = self.account_equity * self.risk_fraction
        
        entry = candidate.executable_entry_price
        sl = intent.logical_stop_loss
        
        if entry == sl or entry == Decimal("0"):
            return SizingDecision(
                sizing_id=str(uuid.uuid4()),
                provisional_quantity=Decimal("0"),
                risk_policy_provenance="v1.0-zero-risk"
            )
            
        risk_per_unit = (entry - sl).copy_abs()
        quantity = risk_amount / risk_per_unit
        
        return SizingDecision(
            sizing_id=str(uuid.uuid4()),
            provisional_quantity=quantity,
            risk_policy_provenance="v1.0-fixed-fraction"
        )
        
    def evaluate_size_aware(self, candidate: PricedCandidate, pre_size: PreSizeEconomics, sizing: SizingDecision) -> SizeAwareEconomics:
        """Computes final impact factoring in actual size against orderbook (if available)."""
        qty = sizing.provisional_quantity
        quote = candidate.quote
        
        # Basic slippage model: If quantity exceeds available top-of-book, add slippage penalty.
        # In a real model, this uses orderbook depths.
        additional_slippage_r = Decimal("0")
        
        # For phase 4 we just stub the additional impact
        if qty > Decimal("10"):
            additional_slippage_r = Decimal("0.05")
            
        total_cost_r = pre_size.pre_size_expected_cost_r + additional_slippage_r
        final_net = pre_size.approved_expected_gross_r - total_cost_r
        
        return SizeAwareEconomics(
            size_aware_cost_r=total_cost_r,
            final_net_ev_r=final_net
        )
        
    def build_final_candidate(
        self, 
        candidate: PricedCandidate, 
        assessment: EvidenceAssessment,
        pre_size: PreSizeEconomics,
        sizing: SizingDecision,
        size_aware: SizeAwareEconomics
    ) -> FinalCandidate:
        """Assembles the final candidate."""
        
        is_eligible = True
        rejection_reason = None
        
        if candidate.rejection_reason:
            is_eligible = False
            rejection_reason = candidate.rejection_reason
        elif assessment.rejection_reason:
            is_eligible = False
            rejection_reason = assessment.rejection_reason
        elif size_aware.final_net_ev_r <= 0:
            is_eligible = False
            rejection_reason = f"Negative or zero FinalNetEV_R: {size_aware.final_net_ev_r}"
            
        return FinalCandidate(
            candidate_id=str(uuid.uuid4()),
            priced_candidate=candidate,
            assessment=assessment,
            pre_size_economics=pre_size,
            sizing=sizing,
            size_aware_economics=size_aware,
            is_eligible=is_eligible,
            rejection_reason=rejection_reason
        )
