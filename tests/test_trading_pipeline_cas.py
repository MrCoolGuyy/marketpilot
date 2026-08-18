import pytest
import time
from decimal import Decimal
import asyncio
from unittest.mock import AsyncMock, MagicMock

from marketpilot.core.factory import MissionControlFactory
from marketpilot.config.settings import AppSettings
from marketpilot.engines.trading_pipeline import TradingPipeline
from marketpilot.models.causal import (
    SnapshotBuildOutcome, SnapshotBuildResult, ClosedInstrumentSnapshot,
    MarketFacts, MarketDataEnvironment, SignalIntent, SignalDirection,
    StrategyIdentity, FinalCandidate, PreSizeEconomics, SizingDecision,
    SizeAwareEconomics, EvidenceAssessment, AssessmentStatus
)
from marketpilot.models.market_data import RawMarketData, AssetType, Ticker
from marketpilot.models.portfolio import PortfolioExposureSnapshot
from marketpilot.core.time import MarketObservationClock

@pytest.fixture
def fake_settings():
    settings = AppSettings()
    settings.scanner.max_results = 1
    settings.scanner.quote_coin = "USDT"
    settings.scanner.min_turnover_24h = Decimal("1000000")
    settings.portfolio.max_total_heat_ratio = Decimal("0.10")
    settings.portfolio.max_simultaneous_lineages = 10
    settings.portfolio.allocated_capital = Decimal("20000")
    return settings

@pytest.mark.asyncio
async def test_cas_orchestration_conflict_recovery(fake_settings, monkeypatch, tmp_path):
    """
    Proves Phase-5 Orchestration CAS semantics:
    1. allocator call #1 receives exposure_version == v1
    2. CAS conflict occurs (reserve_if_version_matches returns False)
    3. PREPARE event is durably closed by ABORT event
    4. allocator call #2 receives exposure_version == v2
    5. CAS success on retry
    """
    ctx = MissionControlFactory.build_runtime(fake_settings)

    # 1. Setup mock pipeline components to get exactly 1 eligible candidate
    raw_mock = RawMarketData(
        symbol="BTCUSDT",
        ticker=Ticker(
            symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="100", bid_price="100", ask_price="101",
            high_24h="100", low_24h="100", price_change_percent_24h="1", volume_24h="100", turnover_24h="10000000", timestamp=time.time()
        ),
        klines=[],
        timestamp=time.time()
    )
    ctx.market_data_fetcher.fetch_scan_candidates = AsyncMock(return_value=[raw_mock])

    # Mock snapshot_builder.build() to return an InstrumentSnapshot for scanner ranking
    from marketpilot.models.scanner import InstrumentSnapshot as ScannerSnapshot, ScannerResult
    from marketpilot.models.core import EngineMetadata
    fake_scanner_snap = ScannerSnapshot(
        symbol="BTCUSDT", last_price=Decimal("100"),
        liquidity_turnover_24h=Decimal("10000000"), volume_24h=Decimal("100"),
        spread_bps=Decimal("10"), atr_percent=Decimal("0.02"),
        momentum_24h=Decimal("1"), trend_strength=Decimal("0.5"),
        trend_age_candles=10,
    )
    ctx.snapshot_builder.build = MagicMock(return_value=fake_scanner_snap)

    # Mock scanner to always include BTCUSDT in top_candidates
    ctx.scanner.evaluate = MagicMock(return_value=ScannerResult(
        top_candidates=[fake_scanner_snap],
        market_health=Decimal("80"),
        timestamp=time.time(),
    ))

    # Mock indicator.calculate to return a valid (but minimal) IndicatorSeries
    ctx.indicator.calculate = MagicMock(return_value=MagicMock())

    original_build_causal = ctx.snapshot_builder.build_causal
    def mock_build_causal(*args, **kwargs):
        facts = MarketFacts(open=Decimal(100), high=Decimal(100), low=Decimal(100), close=Decimal(100), volume=Decimal(0), turnover=Decimal(0),
                            spread_bps=Decimal(0), atr_percent=Decimal(0), momentum_24h=Decimal(0), trend_strength=Decimal(0), trend_age_candles=0)
        snap = ClosedInstrumentSnapshot(snapshot_id="snap_1", symbol="BTCUSDT", interval="60", environment=MarketDataEnvironment.MAINNET,
                                        candle_open_time=0, candle_close_time=0, creation_timestamp=time.time(), feature_set_version="1", facts=facts)
        return SnapshotBuildResult(outcome=SnapshotBuildOutcome.BUILT, snapshot=snap)
    ctx.snapshot_builder.build_causal = mock_build_causal

    def mock_strategy_evaluate(*args, **kwargs):
        ident = StrategyIdentity(registry_version="1", strategy_id="test", strategy_version="1", parameter_set_id="test")
        ts = time.time()
        intent = SignalIntent(intent_id="intent_1", identity=ident, direction=SignalDirection.LONG, symbol="BTCUSDT", signal_timestamp=ts, signal_timestamp_us=int(Decimal(str(ts)) * 1000000),
                              logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("110"), provenance_snapshot_id="snap_1")
        return [intent], MagicMock()
    ctx.strategy.evaluate = mock_strategy_evaluate

    async def mock_get_tickers(*args, **kwargs):
        return [Ticker(symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="100", bid_price="100", ask_price="101",
                       high_24h="100", low_24h="100", price_change_percent_24h="1", volume_24h="100", turnover_24h="100", timestamp=time.time())]
    ctx.client.get_tickers = mock_get_tickers

    # Force the causal pipeline to yield an eligible candidate unconditionally
    # Build a fully valid FinalCandidate that will reach Phase-5
    pipeline = TradingPipeline(ctx)

    from marketpilot.models.causal import PricedCandidate, ExecutableQuoteSnapshot, PricingStatus
    from marketpilot.strategy.pipeline import EvaluationBatchResult

    def fake_process(*args, **kwargs):
        ident = StrategyIdentity(registry_version="1", strategy_id="test", strategy_version="1", parameter_set_id="test")
        ts = time.time()
        intent = SignalIntent(
            intent_id="intent_1", identity=ident, direction=SignalDirection.LONG,
            symbol="BTCUSDT", signal_timestamp=ts,
            signal_timestamp_us=int(Decimal(str(ts)) * 1000000),
            logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("110"),
            provenance_snapshot_id="snap_1",
        )
        priced = PricedCandidate(
            candidate_id="pc_1", intent=intent,
            quote=ExecutableQuoteSnapshot(
                quote_id="q", symbol="BTCUSDT", environment=MarketDataEnvironment.MAINNET,
                quote_timestamp=ts, bid=Decimal("100"), ask=Decimal("101"),
            ),
            executable_entry_price=Decimal("101"),
            pricing_status=PricingStatus.PRICED,
        )
        candidate = FinalCandidate(
            candidate_id="cand_1", priced_candidate=priced,
            assessment=EvidenceAssessment(assessment_id="1", status=AssessmentStatus.VALIDATED, evidence=None),
            pre_size_economics=PreSizeEconomics(
                approved_expected_gross_r=Decimal("0.5"), pre_size_expected_cost_r=Decimal("0.01"),
                pre_size_net_ev_r=Decimal("0.49"), cost_model_provenance="test",
            ),
            sizing=SizingDecision(
                sizing_id="1", provisional_quantity=Decimal("1"),
                effective_stop_price=Decimal("90"), risk_policy_provenance="test",
            ),
            size_aware_economics=SizeAwareEconomics(size_aware_cost_r=Decimal("0.01"), final_net_ev_r=Decimal("0.48")),
            is_eligible=True,
        )
        return EvaluationBatchResult(candidates=[candidate], observations=[])
    pipeline.causal_pipeline.process_signals = fake_process

    # 2. Intercept ExposureManager to fake a CAS failure on attempt 1, success on attempt 2
    attempts = 0
    captured_versions_in_allocator = []

    # Mock snapshot generation to return different versions
    original_snapshot = ctx.exposure.snapshot
    def fake_snapshot():
        snap = original_snapshot()
        return PortfolioExposureSnapshot(
            exposure_version=f"v{attempts + 1}",
            timestamp=snap.timestamp,
            active_risk_amount=snap.active_risk_amount,
            reserved_risk_amount=snap.reserved_risk_amount,
            active_position_ids=snap.active_position_ids,
            reserved_allocation_ids=snap.reserved_allocation_ids,
            policy_limit_risk_amount=snap.policy_limit_risk_amount,
            policy_max_lineages=snap.policy_max_lineages
        )
    ctx.exposure.snapshot = fake_snapshot

    def fake_reserve(allocation_id: str, required_version: str, risk: Decimal):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            assert required_version == "v1"
            return False # Conflict!
        elif attempts == 2:
            assert required_version == "v2"
            return True
        return False
    ctx.exposure.reserve_if_version_matches = fake_reserve

    # 3. Intercept PortfolioAllocator to spy on the version it receives
    from marketpilot.engines.portfolio_allocator import PortfolioAllocator
    original_evaluate = PortfolioAllocator.evaluate_candidate
    def spy_evaluate_candidate(candidate, exposure_snapshot, equity_snapshot, policy):
        captured_versions_in_allocator.append(exposure_snapshot.exposure_version)
        return original_evaluate(candidate, exposure_snapshot, equity_snapshot, policy)
    monkeypatch.setattr(PortfolioAllocator, "evaluate_candidate", spy_evaluate_candidate)

    # 4. Intercept AllocationCommitter to record events
    journal_events = []
    original_prepare = pipeline.allocation_committer.prepare_reservation
    original_commit = pipeline.allocation_committer.commit_allocation
    original_abort = pipeline.allocation_committer.abort_reservation

    def spy_prepare(token):
        journal_events.append(("PREPARE", token.reservation_identity))
        original_prepare(token)
    def spy_commit(token):
        journal_events.append(("COMMIT", token.reservation_identity))
        return original_commit(token)
    def spy_abort(alloc_id, reason):
        journal_events.append(("ABORT", alloc_id))
        original_abort(alloc_id, reason)

    pipeline.allocation_committer.prepare_reservation = spy_prepare
    pipeline.allocation_committer.commit_allocation = spy_commit
    pipeline.allocation_committer.abort_reservation = spy_abort

    from marketpilot.models.mission_control import PipelineContext
    from datetime import datetime

    fake_ctx = PipelineContext(
        decision_id="test_decision",
        cycle_id="test_cycle",
        config_hash="test_hash",
        market_time=datetime.utcnow(),
        start_time=time.time(),
        daemon_instance_id="test_daemon",
    )

    class FakeEvent:
        ctx = fake_ctx

    await pipeline._on_cycle_started(FakeEvent())

    # Assertions
    assert attempts == 2, "CAS should have been attempted exactly twice"
    assert captured_versions_in_allocator == ["v1", "v2"], "Allocator did not receive incrementing versions"

    # Assert journal events order: PREPARE -> ABORT -> PREPARE -> COMMIT
    assert len(journal_events) == 4
    assert journal_events[0][0] == "PREPARE"
    assert journal_events[1][0] == "ABORT"
    assert journal_events[1][1] == journal_events[0][1] # Same allocation_id aborted

    assert journal_events[2][0] == "PREPARE"
    assert journal_events[3][0] == "COMMIT"
    assert journal_events[3][1] == journal_events[2][1]
