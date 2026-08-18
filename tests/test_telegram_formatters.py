import pytest
from decimal import Decimal
from marketpilot.notifications.telegram_formatters import (
    format_system_status,
    format_phase4_cycle,
    format_phase5_admission,
    format_portfolio_rejection,
    format_evidence_rejection,
    format_safety_alert
)
from marketpilot.models.causal import (
    FinalCandidate, PricedCandidate, SignalIntent, StrategyIdentity, SignalDirection,
    ExecutableQuoteSnapshot, PricingStatus, EvidenceAssessment, AssessmentStatus,
    PreSizeEconomics, SizingDecision, SizeAwareEconomics, Interval
)
from marketpilot.models.portfolio import (
    PortfolioAdmissionDecision, PortfolioExposureSnapshot, EquitySnapshot, PortfolioAllocationToken, AllocationRejection
)

@pytest.fixture
def sample_candidate_objects():
    test_candidate = FinalCandidate(
        candidate_id="test_cand_1",
        priced_candidate=PricedCandidate(
            candidate_id="test_cand_1",
            intent=SignalIntent(
                intent_id="test_int_1",
                identity=StrategyIdentity(
                    strategy_id="TEST_STRAT",
                    strategy_version="1.0",
                    registry_version="1.0",
                    parameter_set_id="default"
                ),
                symbol="BTCUSDT",
                timeframe=Interval.M5,
                direction=SignalDirection.LONG,
                signal_timestamp=0.0,
                signal_timestamp_us=0,
                logical_stop_loss=Decimal("49000"),
                logical_take_profit=Decimal("55000"),
                provenance_snapshot_id="test_prov"
            ),
            quote=ExecutableQuoteSnapshot(
                quote_id="test_q_1",
                environment="MAINNET",
                quote_timestamp=0.0,
                symbol="BTCUSDT",
                bid=Decimal("50000"),
                ask=Decimal("50000")
            ),
            pricing_status=PricingStatus.PRICED,
            executable_entry_price=Decimal("50000")
        ),
        assessment=EvidenceAssessment(
            assessment_id="test_ass",
            status=AssessmentStatus.VALIDATED,
            approved_expected_gross_r=Decimal("1.5")
        ),
        pre_size_economics=PreSizeEconomics(
            approved_expected_gross_r=Decimal("1.5"),
            pre_size_expected_cost_r=Decimal("0.1"),
            pre_size_net_ev_r=Decimal("1.4"),
            cost_model_provenance="TEST"
        ),
        sizing=SizingDecision(
            sizing_id="test_size",
            provisional_quantity=Decimal("0.05"),
            effective_stop_price=Decimal("49000"),
            risk_policy_provenance="TEST"
        ),
        size_aware_economics=SizeAwareEconomics(
            size_aware_cost_r=Decimal("0.1"),
            final_net_ev_r=Decimal("1.4")
        ),
        is_eligible=True
    )

    test_decision = PortfolioAdmissionDecision(
        decision_id="test_dec",
        is_admitted=True,
        token=PortfolioAllocationToken(
            candidate_id="test_cand_1",
            decision_id="test_dec",
            strategy_id="TEST_STRAT",
            strategy_version="1.0",
            parameter_set_id="default",
            symbol="BTCUSDT",
            direction="LONG",
            sizing_id="test_size",
            effective_stop=Decimal("49000"),
            quantity=Decimal("0.05"),
            executable_entry=Decimal("50000"),
            candidate_risk_amount=Decimal("50.0"),
            final_net_ev=Decimal("1.4"),
            portfolio_snapshot_version="v1",
            equity_snapshot_version="v1",
            portfolio_policy_version="v1",
            reservation_identity="test_res",
            lineage_identity="test_lin",
            admission_timestamp=0.0
        )
    )

    test_exposure = PortfolioExposureSnapshot(
        exposure_version="v1",
        timestamp=0.0,
        active_position_ids=("pos_1",),
        reserved_allocation_ids=(),
        active_risk_amount=Decimal("150.0"),
        reserved_risk_amount=Decimal("0.0"),
        policy_limit_risk_amount=Decimal("1000.0"),
        policy_max_lineages=5,

    )

    test_equity = EquitySnapshot(
        snapshot_id="test_eq",
        version="1.0",
        captured_at=0.0,
        environment="PAPER",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("10000.0"),
        usable_account_value=Decimal("15000.0"),
        effective_risk_capital=Decimal("10000.0"),
        freshness_status="FRESH",
        provenance="TEST"
    )

    return test_candidate, test_decision, test_exposure, test_equity


def test_format_system_status():
    result = format_system_status("ACTIVE", "PAPER", "MAINNET", "1.0")
    assert "<b>System Status</b>" in result
    assert "<code>ACTIVE</code>" in result

def test_format_phase4_cycle():
    result = format_phase4_cycle("c1", "0.0", "PAPER", "MAINNET", "SUCCESS", 5, 5, 2, 2, 2, 1, 1, 0, 0, 0, 0, 0)
    assert "<b>Cycle Summary</b>" in result
    assert "Portfolio Admitted: 1" in result

def test_format_phase5_admission(sample_candidate_objects):
    result = format_phase5_admission(*sample_candidate_objects)
    assert "MARKETPILOT — TRADE CANDIDATE" in result
    assert "<b>BTCUSDT — LONG</b>" in result
    assert "<code>50.00</code> USDT" in result

def test_format_portfolio_rejection(sample_candidate_objects):
    cand, _, exp, _ = sample_candidate_objects
    rej_dec = PortfolioAdmissionDecision(
        decision_id="test_dec",
        is_admitted=False,
        rejection=AllocationRejection(decision_id="test_dec", rejection_code="HEAT", reason="Too much heat")
    )
    result = format_portfolio_rejection(cand, rej_dec, exp)
    assert "<b>Portfolio Rejection</b>" in result
    assert "Too much heat" in result

def test_format_evidence_rejection():
    result = format_evidence_rejection("ETHUSDT", "SHORT", "TEST v1", Decimal("2000.0"), "NO_EVIDENCE", "Missing")
    assert "<b>Evidence Rejection</b>" in result
    assert "ETHUSDT" in result

def test_format_safety_alert():
    result = format_safety_alert("RecoveryEngine", "STATE_MISMATCH")
    assert "<b>SAFETY ALERT</b>" in result
    assert "<pre>STATE_MISMATCH</pre>" in result
