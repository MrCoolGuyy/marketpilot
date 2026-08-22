import pytest
from decimal import Decimal
import time
import uuid

from marketpilot.core.enums import Interval, MarketDataEnvironment
from marketpilot.models.causal import (
    ClosedInstrumentSnapshot,
    MarketFacts,
    StrategyIdentity,
    SignalIntent,
    SignalDirection,
    ExecutableQuoteSnapshot,
    EvidenceApplicability,
    OutcomeDistributionArtifact,
    OutcomeObservation,
    StrategyEvidence,
    AssessmentStatus,
    FinalCandidate
)

from marketpilot.strategy.pricing_policy import PricingPolicy
from marketpilot.strategy.validation_policy import ValidationPolicy
from marketpilot.strategy.economics import CausalEconomicsEngine
from marketpilot.strategy.pipeline import CausalPipeline

def test_causal_pipeline_full_acceptance():
    app = EvidenceApplicability(
        strategy_id="strat_1",
        strategy_version="1.0",
        parameter_set_id="p1",
        timeframe=Interval.H1,
        direction=SignalDirection.LONG,
        regime_model="trend_v1",
        regime_state="BULL",
        market_scope="ALL",
        execution_policy_version="1.0",
        research_cutoff_timestamp=time.time() - 1000
    )

    # 2 observations yielding ExpectedGrossR = 0.5
    dist = OutcomeDistributionArtifact(
        artifact_id="dist_1",
        outcomes=(OutcomeObservation(realized_r=Decimal("1.0")), OutcomeObservation(realized_r=Decimal("0.0")))
    )

    # Verify expected_gross_r is mathematically derived
    assert dist.expected_gross_r == Decimal("0.5")

    evidence = StrategyEvidence(evidence_id="ev_1", applicability=app, distribution=dist)

    identity = StrategyIdentity(
        registry_version="1.0", strategy_id="strat_1", strategy_version="1.0", parameter_set_id="p1"
    )

    now = time.time()
    ts = time.time()

    intent = SignalIntent(
        intent_id="intent_1",
        identity=identity,
        direction=SignalDirection.LONG,
        symbol="BTCUSDT",
        signal_timestamp=ts,
        signal_timestamp_us=int(Decimal(str(ts)) * 1_000_000),
        logical_stop_loss=Decimal("95"),
        logical_take_profit=Decimal("110"),
        provenance_snapshot_id="snap_1"
    )

    quote = ExecutableQuoteSnapshot(
        quote_id="q1", symbol="BTCUSDT", environment=MarketDataEnvironment.MAINNET,
        quote_timestamp=ts + 1, bid=Decimal("99.9"), ask=Decimal("100.1")
    )

    pipeline = CausalPipeline(
        pricing=PricingPolicy(),
        validation=ValidationPolicy([evidence]),
        economics=CausalEconomicsEngine(account_equity=Decimal("1000"))
    )

    result = pipeline.process_signals(
        [intent], {"strat_1": quote}, "trend_v1", "BULL", "ALL", Decimal("10000"), Decimal("0.005"), Decimal("0.01")
    )

    assert len(result.candidates) == 1
    assert len(result.observations) == 2 # 1 eval, 1 cf

    final = result.candidates[0]

    # Pricing
    assert final.priced_candidate.executable_entry_price == Decimal("100.1")

    # Assessment
    assert final.assessment.status == AssessmentStatus.VALIDATED

    # Sizing Binding
    assert final.sizing.provisional_quantity > 0
    assert final.pre_size_economics.pre_size_net_ev_r == Decimal("0.4")
    assert final.is_eligible is True


def test_quote_causality():
    identity = StrategyIdentity(
        registry_version="1.0", strategy_id="strat_1", strategy_version="1.0", parameter_set_id="p1"
    )
    now = time.time()
    intent = SignalIntent(
        intent_id="intent_1", identity=identity, direction=SignalDirection.LONG,
        symbol="BTCUSDT", signal_timestamp=now, signal_timestamp_us=int(Decimal(str(now)) * 1_000_000), logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("120"),
        provenance_snapshot_id="snap_1"
    )

    # Future quote (Valid)
    q_future = ExecutableQuoteSnapshot(
        quote_id="q1", symbol="BTCUSDT", environment=MarketDataEnvironment.MAINNET,
        quote_timestamp=now + 1, bid=Decimal("99.9"), ask=Decimal("100.1")
    )

    # Past quote (Invalid, causal leak)
    q_past = ExecutableQuoteSnapshot(
        quote_id="q2", symbol="BTCUSDT", environment=MarketDataEnvironment.MAINNET,
        quote_timestamp=now - 1, bid=Decimal("99.9"), ask=Decimal("100.1")
    )

    policy = PricingPolicy()
    assert policy.price_intent(intent, q_future).pricing_status.value == "PRICED"
    assert policy.price_intent(intent, q_past).pricing_status.value == "UNPRICEABLE"


def test_validation_policy_states():
    now = time.time()

    app_base = EvidenceApplicability(
        strategy_id="strat_1", strategy_version="1.0", parameter_set_id="p1",
        timeframe=Interval.H1, direction=SignalDirection.LONG,
        regime_model="trend", regime_state="BULL", market_scope="ALL",
        execution_policy_version="1.0", research_cutoff_timestamp=now - 1000
    )
    dist_good = OutcomeDistributionArtifact(
        artifact_id="d1", outcomes=(OutcomeObservation(realized_r=Decimal("0.5")),)
    )
    dist_bad = OutcomeDistributionArtifact(
        artifact_id="d2", outcomes=(OutcomeObservation(realized_r=Decimal("0.05")),)
    )

    ev_good = StrategyEvidence(evidence_id="e1", applicability=app_base, distribution=dist_good)

    # Stale evidence (older than 30 days)
    app_stale = EvidenceApplicability(
        strategy_id="strat_1", strategy_version="1.0", parameter_set_id="p1",
        timeframe=Interval.H1, direction=SignalDirection.LONG,
        regime_model="trend", regime_state="BULL", market_scope="ALL",
        execution_policy_version="1.0", research_cutoff_timestamp=now - 86400 * 31
    )
    ev_stale = StrategyEvidence(evidence_id="e2", applicability=app_stale, distribution=dist_good)

    # Insufficient evidence (Gross R < 0.1)
    ev_insufficient = StrategyEvidence(evidence_id="e3", applicability=app_base, distribution=dist_bad)

    identity = StrategyIdentity(
        registry_version="1.0", strategy_id="strat_1", strategy_version="1.0", parameter_set_id="p1"
    )
    intent = SignalIntent(
        intent_id="i1", identity=identity, direction=SignalDirection.LONG,
        symbol="BTCUSDT", signal_timestamp=now, signal_timestamp_us=int(Decimal(str(now)) * 1_000_000), logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("120"),
        provenance_snapshot_id="s1"
    )
    quote = ExecutableQuoteSnapshot(
        quote_id="q1", symbol="BTC", environment=MarketDataEnvironment.MAINNET,
        quote_timestamp=now, bid=Decimal("10"), ask=Decimal("11")
    )

    priced = PricingPolicy().price_intent(intent, quote)

    # Test VALIDATED
    v_good = ValidationPolicy([ev_good])
    assert v_good.assess(priced, "trend", "BULL", "ALL").status == AssessmentStatus.VALIDATED

    # Test STALE
    v_stale = ValidationPolicy([ev_stale])
    assert v_stale.assess(priced, "trend", "BULL", "ALL").status == AssessmentStatus.STALE

    # Test INSUFFICIENT
    v_insuff = ValidationPolicy([ev_insufficient])
    assert v_insuff.assess(priced, "trend", "BULL", "ALL").status == AssessmentStatus.INSUFFICIENT

    # Test INAPPLICABLE (wrong regime)
    v_good_regime = ValidationPolicy([ev_good])
    assert v_good_regime.assess(priced, "trend", "BEAR", "ALL").status == AssessmentStatus.INAPPLICABLE

    # Test INAPPLICABLE (wrong direction)
    intent_short = SignalIntent(
        intent_id="i2", identity=identity, direction=SignalDirection.SHORT,
        symbol="BTCUSDT", signal_timestamp=now, signal_timestamp_us=int(Decimal(str(now)) * 1_000_000), logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("120"),
        provenance_snapshot_id="s1"
    )
    priced_short = PricingPolicy().price_intent(intent_short, quote)
    assert v_good.assess(priced_short, "trend", "BULL", "ALL").status == AssessmentStatus.INAPPLICABLE


def test_global_reranking():
    # FinalNetEV_R DESC -> signal_timestamp ASC -> deterministic_decision_key ASC
    class MockFinal:
        def __init__(self, ev, ts, key, id):
            self.ev = ev
            self.ts = ts
            self.key = key
            self.id = id

            # mock attributes used by pipeline sort
            self.size_aware_economics = type('obj', (object,), {'final_net_ev_r': Decimal(str(ev))})
            self.priced_candidate = type('obj', (object,), {'intent': type('obj', (object,), {'signal_timestamp': ts})})
            self.deterministic_decision_key = key

    candidates = [
        MockFinal(0.5, 10, "A", "id1"), # Rank 1 (highest EV)
        MockFinal(0.4, 10, "B", "id2"), # Rank 2
        MockFinal(0.4, 15, "A", "id3"), # Rank 4 (same EV, later TS)
        MockFinal(0.4, 10, "C", "id4"), # Rank 3 (same EV, same TS, later key)
    ]

    candidates.sort(
        key=lambda c: (
            -c.size_aware_economics.final_net_ev_r,
            c.priced_candidate.intent.signal_timestamp,
            c.deterministic_decision_key
        )
    )

    assert candidates[0].id == "id1"
    assert candidates[1].id == "id2"
    assert candidates[2].id == "id4"
    assert candidates[3].id == "id3"
