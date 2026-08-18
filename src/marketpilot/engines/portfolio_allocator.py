"""
MarketPilot Engines - Portfolio Allocator.

Deterministic pure admission engine that evaluates FinalCandidates
against PortfolioPolicy, Exposure, and Equity state.
"""

from __future__ import annotations

import uuid
import hashlib
import json
from typing import Optional
from marketpilot.models.causal import FinalCandidate
from marketpilot.models.portfolio import (
    PortfolioExposureSnapshot,
    EquitySnapshot,
    PortfolioAdmissionDecision,
    PortfolioAllocationToken,
    AllocationRejection
)
from marketpilot.strategy.portfolio_policy import PortfolioPolicy

class PortfolioAllocator:
    """
    Pure admission engine for Phase 5.
    Evaluates whether a candidate can receive capital based on current exposure.
    """

    @staticmethod
    def evaluate_candidate(
        candidate: FinalCandidate,
        exposure_snapshot: PortfolioExposureSnapshot,
        equity_snapshot: EquitySnapshot,
        policy: PortfolioPolicy
    ) -> PortfolioAdmissionDecision:
        """
        Pure function evaluating a candidate against the canonical exposure and equity state.
        """
        decision_id = str(uuid.uuid4())

        # 1. Deterministic Lineage Identity
        # Use deterministic canonical serialization + SHA-256 using signal_timestamp_us
        lineage_payload = ["v1", candidate.deterministic_decision_key, candidate.priced_candidate.intent.signal_timestamp_us]
        raw_key = json.dumps(lineage_payload, separators=(',', ':'))
        lineage_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
        allocation_id = f"{candidate.priced_candidate.intent.symbol}:{lineage_hash}"

        # 2. Lineage Check
        # ONE ACTIVE LOGICAL LINEAGE PER INSTRUMENT
        # Determine if this instrument already has an active or reserved lineage
        symbol = candidate.priced_candidate.intent.symbol

        for active_id in exposure_snapshot.active_position_ids:
            if active_id.startswith(f"{symbol}:"):
                return PortfolioAdmissionDecision(
                    decision_id=decision_id,
                    is_admitted=False,
                    rejection=AllocationRejection(
                        decision_id=decision_id,
                        rejection_code="REJECTED_ACTIVE_LINEAGE",
                        reason=f"Instrument {symbol} already has an active position"
                    )
                )

        for alloc_id in exposure_snapshot.reserved_allocation_ids:
            if alloc_id.startswith(f"{symbol}:"):
                return PortfolioAdmissionDecision(
                    decision_id=decision_id,
                    is_admitted=False,
                    rejection=AllocationRejection(
                        decision_id=decision_id,
                        rejection_code="REJECTED_ACTIVE_LINEAGE",
                        reason=f"Instrument {symbol} already has a pending reservation"
                    )
                )

        # 3. Sizing Validation (Effective Stop Proof)
        quantity = candidate.sizing.provisional_quantity
        entry_price = candidate.priced_candidate.executable_entry_price
        stop_loss = candidate.sizing.effective_stop_price

        import math
        if not stop_loss or not math.isfinite(float(stop_loss)) or stop_loss <= 0:
            return PortfolioAdmissionDecision(
                decision_id=decision_id,
                is_admitted=False,
                rejection=AllocationRejection(
                    decision_id=decision_id,
                    rejection_code="REJECTED_INVALID_CAUSAL_STOP",
                    reason="effective_stop_price is missing, non-finite, or <= 0"
                )
            )

        if candidate.priced_candidate.intent.direction.value == "LONG" and stop_loss >= entry_price:
            return PortfolioAdmissionDecision(
                decision_id=decision_id,
                is_admitted=False,
                rejection=AllocationRejection(
                    decision_id=decision_id,
                    rejection_code="REJECTED_INVALID_CAUSAL_STOP",
                    reason=f"LONG stop {stop_loss} >= entry {entry_price}"
                )
            )
        elif candidate.priced_candidate.intent.direction.value == "SHORT" and stop_loss <= entry_price:
            return PortfolioAdmissionDecision(
                decision_id=decision_id,
                is_admitted=False,
                rejection=AllocationRejection(
                    decision_id=decision_id,
                    rejection_code="REJECTED_INVALID_CAUSAL_STOP",
                    reason=f"SHORT stop {stop_loss} <= entry {entry_price}"
                )
            )

        # 4. Heat Check

        candidate_risk = quantity * abs(entry_price - stop_loss)
        projected_total_risk = exposure_snapshot.total_risk_amount + candidate_risk

        # Guard against zero equity
        if equity_snapshot.effective_risk_capital <= 0:
            return PortfolioAdmissionDecision(
                decision_id=decision_id,
                is_admitted=False,
                rejection=AllocationRejection(
                    decision_id=decision_id,
                    rejection_code="REJECTED_ZERO_EQUITY",
                    reason="Effective risk capital is zero or negative."
                )
            )

        projected_heat_ratio = projected_total_risk / equity_snapshot.effective_risk_capital

        if projected_heat_ratio > policy.max_total_heat_ratio:
            return PortfolioAdmissionDecision(
                decision_id=decision_id,
                is_admitted=False,
                rejection=AllocationRejection(
                    decision_id=decision_id,
                    rejection_code="REJECTED_PORTFOLIO_HEAT",
                    reason=f"Projected heat ratio {projected_heat_ratio:.4f} exceeds policy max {policy.max_total_heat_ratio:.4f}"
                )
            )

        # 5. Global Lineage Count Check
        total_lineages = len(exposure_snapshot.active_position_ids) + len(exposure_snapshot.reserved_allocation_ids)
        if total_lineages >= policy.max_simultaneous_lineages:
            return PortfolioAdmissionDecision(
                decision_id=decision_id,
                is_admitted=False,
                rejection=AllocationRejection(
                    decision_id=decision_id,
                    rejection_code="REJECTED_MAX_LINEAGES",
                    reason=f"Total active/reserved lineages {total_lineages} >= max {policy.max_simultaneous_lineages}"
                )
            )

        # 6. Admitted! Generate Allocation Token
        import time
        token = PortfolioAllocationToken(
            candidate_id=candidate.candidate_id,
            decision_id=decision_id,
            strategy_id=candidate.priced_candidate.intent.identity.strategy_id,
            strategy_version=candidate.priced_candidate.intent.identity.strategy_version,
            parameter_set_id=candidate.priced_candidate.intent.identity.parameter_set_id,
            symbol=symbol,
            direction=candidate.priced_candidate.intent.direction.value,
            sizing_id=candidate.sizing.sizing_id if hasattr(candidate.sizing, "sizing_id") else candidate.sizing.decision_id,
            effective_stop=candidate.sizing.effective_stop_price,
            quantity=candidate.sizing.provisional_quantity,
            executable_entry=candidate.priced_candidate.executable_entry_price,
            candidate_risk_amount=candidate_risk,
            final_net_ev=candidate.size_aware_economics.final_net_ev_r,
            portfolio_snapshot_version=exposure_snapshot.exposure_version,
            equity_snapshot_version=equity_snapshot.version,
            portfolio_policy_version=policy.policy_version,
            reservation_identity=allocation_id,
            lineage_identity=lineage_hash,
            admission_timestamp=time.time()
        )

        return PortfolioAdmissionDecision(
            decision_id=decision_id,
            is_admitted=True,
            token=token
        )
