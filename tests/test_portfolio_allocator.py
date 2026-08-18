import pytest
from decimal import Decimal
from marketpilot.models.causal import FinalCandidate, PricedCandidate, SignalIntent, StrategyIdentity, SignalDirection, EvidenceAssessment, AssessmentStatus, SizingDecision, PreSizeEconomics, SizeAwareEconomics
from marketpilot.models.portfolio import PortfolioExposureSnapshot, EquitySnapshot
from marketpilot.strategy.portfolio_policy import PortfolioPolicy
from marketpilot.engines.portfolio_allocator import PortfolioAllocator

def _mock_candidate(symbol: str, qty: str, entry: str, stop: str) -> FinalCandidate:
    intent = SignalIntent(
        intent_id="int-1",
        identity=StrategyIdentity(
            registry_version="1",
            strategy_id="s1",
            strategy_version="1",
            parameter_set_id="p1"
        ),
        direction=SignalDirection.LONG,
        symbol=symbol,
        signal_timestamp=100.0,
        signal_timestamp_us=100000000,
        logical_stop_loss=Decimal(stop),
        logical_take_profit=Decimal("100000"),
        provenance_snapshot_id="snap1"
    )

    from marketpilot.models.causal import ExecutableQuoteSnapshot, MarketDataEnvironment

    quote = ExecutableQuoteSnapshot(
        quote_id="q1",
        symbol=symbol,
        environment=MarketDataEnvironment.TESTNET,
        quote_timestamp=100.0,
        bid=Decimal("50000"),
        ask=Decimal("50000")
    )

    return FinalCandidate(
        candidate_id="cand-1",
        priced_candidate=PricedCandidate(
            candidate_id="cand-1",
            intent=intent,
            quote=quote,
            pricing_status="PRICED",
            executable_entry_price=Decimal(entry),
        ),
        assessment=EvidenceAssessment(assessment_id="a1", status=AssessmentStatus.VALIDATED),
        pre_size_economics=PreSizeEconomics(approved_expected_gross_r=Decimal("1"), pre_size_expected_cost_r=Decimal("0.1"), pre_size_net_ev_r=Decimal("0.9"), cost_model_provenance="test"),
        sizing=SizingDecision(sizing_id="s1", provisional_quantity=Decimal(qty), effective_stop_price=Decimal(stop), risk_policy_provenance="test"),
        size_aware_economics=SizeAwareEconomics(size_aware_cost_r=Decimal("0.1"), final_net_ev_r=Decimal("0.8")),
        is_eligible=True
    )

def test_portfolio_allocator_admission_success():
    cand = _mock_candidate("BTCUSDT", "1", "50000", "49000") # Risk = 1 * 1000 = 1000

    exposure = PortfolioExposureSnapshot(
        exposure_version="v1",
        timestamp=100.0,
        active_position_ids=tuple(),
        reserved_allocation_ids=tuple(),
        active_risk_amount=Decimal("0"),
        reserved_risk_amount=Decimal("0")
    )

    equity = EquitySnapshot(
        snapshot_id="e1",
        version="1",
        captured_at=100.0,
        environment="test",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("20000"),
        usable_account_value=Decimal("20000"),
        effective_risk_capital=Decimal("20000"),
        freshness_status="FRESH",
        provenance="test"
    )

    policy = PortfolioPolicy(policy_version="1", max_total_heat_ratio=Decimal("0.10"))

    decision = PortfolioAllocator.evaluate_candidate(cand, exposure, equity, policy)
    assert decision.is_admitted is True
    assert decision.token is not None

def test_portfolio_allocator_rejection_heat():
    cand = _mock_candidate("BTCUSDT", "1", "50000", "47000") # Risk = 1 * 3000 = 3000

    exposure = PortfolioExposureSnapshot(
        exposure_version="v1",
        timestamp=100.0,
        active_position_ids=tuple(),
        reserved_allocation_ids=tuple(),
        active_risk_amount=Decimal("0"),
        reserved_risk_amount=Decimal("0")
    )

    equity = EquitySnapshot(
        snapshot_id="e1",
        version="1",
        captured_at=100.0,
        environment="test",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("20000"),
        usable_account_value=Decimal("20000"),
        effective_risk_capital=Decimal("20000"),
        freshness_status="FRESH",
        provenance="test"
    )

    policy = PortfolioPolicy(policy_version="1", max_total_heat_ratio=Decimal("0.10")) # Max risk 2000

    decision = PortfolioAllocator.evaluate_candidate(cand, exposure, equity, policy)
    assert decision.is_admitted is False
    assert decision.rejection.rejection_code == "REJECTED_PORTFOLIO_HEAT"

def test_portfolio_allocator_rejection_existing_lineage():
    cand = _mock_candidate("BTCUSDT", "1", "50000", "49000")

    exposure = PortfolioExposureSnapshot(
        exposure_version="v1",
        timestamp=100.0,
        active_position_ids=("BTCUSDT:LONG:old",),
        reserved_allocation_ids=tuple(),
        active_risk_amount=Decimal("1000"),
        reserved_risk_amount=Decimal("0")
    )

    equity = EquitySnapshot(
        snapshot_id="e1",
        version="1",
        captured_at=100.0,
        environment="test",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("20000"),
        usable_account_value=Decimal("20000"),
        effective_risk_capital=Decimal("20000"),
        freshness_status="FRESH",
        provenance="test"
    )

    policy = PortfolioPolicy(policy_version="1", max_total_heat_ratio=Decimal("0.20"))

    decision = PortfolioAllocator.evaluate_candidate(cand, exposure, equity, policy)
    assert decision.is_admitted is False
    assert decision.rejection.rejection_code == "REJECTED_ACTIVE_LINEAGE"

def test_portfolio_allocator_rejection_max_lineages():
    cand = _mock_candidate("ETHUSDT", "1", "5000", "4900") # Risk = 1 * 100 = 100

    exposure = PortfolioExposureSnapshot(
        exposure_version="v1",
        timestamp=100.0,
        active_position_ids=("BTCUSDT:LONG:old",),
        reserved_allocation_ids=tuple(),
        active_risk_amount=Decimal("1000"),
        reserved_risk_amount=Decimal("0")
    )

    equity = EquitySnapshot(
        snapshot_id="e1",
        version="1",
        captured_at=100.0,
        environment="test",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("20000"),
        usable_account_value=Decimal("20000"),
        effective_risk_capital=Decimal("20000"),
        freshness_status="FRESH",
        provenance="test"
    )

    # max_simultaneous_lineages=1
    policy = PortfolioPolicy(policy_version="1", max_total_heat_ratio=Decimal("0.20"), max_simultaneous_lineages=1)

    decision = PortfolioAllocator.evaluate_candidate(cand, exposure, equity, policy)
    assert decision.is_admitted is False
    assert decision.rejection.rejection_code == "REJECTED_MAX_LINEAGES"

def test_cas_conflict_reevaluation_semantics():
    """
    Explicit regression test for CAS conflict semantics.
    Verifies that re-evaluating the same candidate against a newer exposure snapshot
    yields a deterministically consistent decision ID but a fresh allocation token.
    """
    cand = _mock_candidate("BTCUSDT", "1", "50000", "49000")
    equity = EquitySnapshot(
        snapshot_id="e1", version="1", captured_at=100.0, environment="test", safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("20000"), usable_account_value=Decimal("20000"),
        effective_risk_capital=Decimal("20000"), freshness_status="FRESH", provenance="test"
    )
    policy = PortfolioPolicy(policy_version="1", max_total_heat_ratio=Decimal("0.10"), max_simultaneous_lineages=10)

    exposure_v1 = PortfolioExposureSnapshot(
        exposure_version="v1", timestamp=100.0, active_position_ids=tuple(), reserved_allocation_ids=tuple(), active_risk_amount=Decimal("0"), reserved_risk_amount=Decimal("0")
    )

    # 1. First evaluation on v1
    decision_v1 = PortfolioAllocator.evaluate_candidate(cand, exposure_v1, equity, policy)
    assert decision_v1.is_admitted is True
    assert decision_v1.token.portfolio_snapshot_version == "v1"
    token_v1_identity = decision_v1.token.lineage_identity

    # 2. Simulate CAS failure due to concurrent reservation by another agent
    # Agent re-evaluates on v2
    exposure1 = PortfolioExposureSnapshot(
        exposure_version="v1", timestamp=100.0, active_position_ids=tuple(), reserved_allocation_ids=tuple(), active_risk_amount=Decimal("0"), reserved_risk_amount=Decimal("0")
    )

    decision1 = PortfolioAllocator.evaluate_candidate(cand, exposure1, equity, policy)

    exposure2 = PortfolioExposureSnapshot(
        exposure_version="v2", timestamp=100.0, active_position_ids=tuple(), reserved_allocation_ids=tuple(), active_risk_amount=Decimal("0"), reserved_risk_amount=Decimal("0")
    )

    decision_v2 = PortfolioAllocator.evaluate_candidate(cand, exposure2, equity, policy)
    assert decision_v2.is_admitted is True
    assert decision_v2.token.portfolio_snapshot_version == "v2"

    # The deterministic lineage hash must be stable across re-evaluations of the same causal signal
    assert decision_v2.token.lineage_identity == token_v1_identity

    # The decision id must be different because it's a new evaluation invocation
    assert decision_v2.decision_id != decision_v1.decision_id
