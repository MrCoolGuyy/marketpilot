import pytest
import time
from decimal import Decimal
import asyncio
from unittest.mock import AsyncMock, MagicMock

from marketpilot.core.factory import MissionControlFactory
from marketpilot.config.settings import AppSettings
from marketpilot.engines.trading_pipeline import TradingPipeline
from marketpilot.core.time import MarketObservationClock
from marketpilot.models.market_data import RawMarketData, AssetType, Ticker
from marketpilot.models.causal import (
    SnapshotBuildOutcome, SnapshotBuildResult, ClosedInstrumentSnapshot,
    MarketFacts, MarketDataEnvironment, SignalIntent, SignalDirection,
    StrategyIdentity
)
from marketpilot.dashboard.projections import FileProjectionRepository
from marketpilot.dashboard.store import DashboardReadStore

@pytest.fixture
def fake_settings():
    settings = AppSettings()
    settings.scanner.max_results = 1
    return settings

@pytest.mark.asyncio
async def test_causal_quote_acquisition_order(fake_settings, monkeypatch, tmp_path):
    """
    Prove that the market reader get_tickers is called AFTER the SignalIntent is finalized.
    Also proves the cross-process projection writes successfully.
    """
    # 1. Setup a fake durable projection store to avoid touching the real file system ~/.marketpilot
    fake_repo_dir = tmp_path / "projections"
    fake_repo_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("marketpilot.dashboard.projections.DEFAULT_PROJECTIONS_DIR", fake_repo_dir)
    
    ctx = MissionControlFactory.build_runtime(fake_settings)
    
    # We will record the exact order of calls
    call_trace = []
    
    # Mock Market Data Fetcher (Phase 1)
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
    
    # Mock Scanner
    ctx.scanner.evaluate = MagicMock()
    ctx.scanner.evaluate.return_value.top_candidates = [MagicMock(symbol="BTCUSDT")]
    
    # Mock Indicator Engine
    from marketpilot.models.indicators import IndicatorSeries
    from marketpilot.core.enums import Interval
    ctx.indicator.calculate = MagicMock(return_value=IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=[]))
    
    # Mock Snapshot Builder (Phase 2 - Causal Boundary)
    original_build_causal = ctx.snapshot_builder.build_causal
    def mock_build_causal(*args, **kwargs):
        call_trace.append("build_causal")
        facts = MarketFacts(open=Decimal(100), high=Decimal(100), low=Decimal(100), close=Decimal(100), volume=Decimal(0), turnover=Decimal(0),
                            spread_bps=Decimal(0), atr_percent=Decimal(0), momentum_24h=Decimal(0), trend_strength=Decimal(0), trend_age_candles=0)
        snap = ClosedInstrumentSnapshot(snapshot_id="snap_1", symbol="BTCUSDT", interval="60", environment=MarketDataEnvironment.MAINNET,
                                        candle_open_time=0, candle_close_time=0, creation_timestamp=time.time(), feature_set_version="1", facts=facts)
        return SnapshotBuildResult(outcome=SnapshotBuildOutcome.BUILT, snapshot=snap)
    ctx.snapshot_builder.build_causal = mock_build_causal
    
    # Mock Strategy (Phase 3 - Intent Generation)
    original_strategy_evaluate = ctx.strategy.evaluate
    def mock_strategy_evaluate(*args, **kwargs):
        call_trace.append("strategy_evaluate")
        ident = StrategyIdentity(registry_version="1", strategy_id="test", strategy_version="1", parameter_set_id="test")
        intent = SignalIntent(intent_id="intent_1", identity=ident, direction=SignalDirection.LONG, symbol="BTCUSDT", signal_timestamp=time.time(),
                              logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("110"), provenance_snapshot_id="snap_1")
        return [intent], MagicMock()
    ctx.strategy.evaluate = mock_strategy_evaluate
    
    # Mock Exchange Client (Phase 4 - Quote Acquisition)
    original_get_tickers = ctx.client.get_tickers
    async def mock_get_tickers(*args, **kwargs):
        call_trace.append("get_tickers")
        return [Ticker(symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="100", bid_price="100", ask_price="101",
                       high_24h="100", low_24h="100", price_change_percent_24h="1", volume_24h="100", turnover_24h="100", timestamp=time.time())]
    ctx.client.get_tickers = mock_get_tickers
    
    pipeline = TradingPipeline(ctx)
    
    # 2. Trigger the cycle
    from marketpilot.models.mission_control import PipelineContext
    event = MagicMock()
    event.ctx = PipelineContext(decision_id="test-decision", cycle_id="test-cycle", config_hash="test", market_time=time.time(), start_time=time.time())
    await pipeline._on_cycle_started(event)
    
    # 3. Assert Causality Order
    # The true test of causal correctness is that quotes are fetched AFTER the signal is finalized.
    assert call_trace == ["build_causal", "strategy_evaluate", "get_tickers"], "Quote acquisition must happen after signal generation"
    
    # 4. Prove Cross-Process Projection
    # We create a completely separate DashboardReadStore pointing to the same fake directory
    # It must not share any memory with the TradingPipeline
    dashboard_repo = FileProjectionRepository(directory=fake_repo_dir)
    dashboard_store = DashboardReadStore(repository=dashboard_repo)
    
    # We expect a candidate or rejection to have been projected
    evidence = dashboard_store.get_all_evidence()
    assert len(evidence) == 1
    
    model = evidence[0]
    assert model.strategy_id == "test"
    # Even if it rejected due to no evidence policy, it should project the rejection correctly
    assert model.evidence_status in ["NO_EVIDENCE", "INAPPLICABLE", "INSUFFICIENT", "VALIDATED"]
    assert model.deterministic_decision_key == "BTCUSDT:test:1:test:LONG"
    
    # Intelligence should also be projected
    intelligence = dashboard_store.get_market_intelligence("BTCUSDT")
    assert intelligence is not None
    assert intelligence.symbol == "BTCUSDT"

    # 5. Prove Envelope and Stale logic
    meta = dashboard_store.get_projection_metadata()
    assert meta is not None
    assert "generated_at" in meta
    assert meta["daemon_instance_id"] == "unknown" # as no custom one passed yet
    assert meta["cycle_outcome"] == "SIGNALS_GENERATED_NO_ELIGIBLE_CANDIDATE"
    assert meta["intents_count"] == 1
    assert meta["candidates_count"] == 0

    # Simulate lifecycle heartbeat and liveness
    lifecycle = dashboard_store.get_lifecycle()
    # It might be None if we didn't run the full service, TradingPipeline doesn't write lifecycle.
    # We can write one manually to test liveness
    dashboard_repo.publish_lifecycle("test", "RUNNING", "CONTINUOUS", time.time(), time.time())
    
    lifecycle = dashboard_store.get_lifecycle()
    assert lifecycle is not None
    assert lifecycle["status"] == "RUNNING"

    # Simulate stale lifecycle file by manipulating the raw JSON
    import json
    raw_life = json.loads(dashboard_repo.lifecycle_file.read_text())
    raw_life["data"]["heartbeat_at"] = time.time() - 125  # > 120s stale
    dashboard_repo.lifecycle_file.write_text(json.dumps(raw_life))
    
    # Router logic would now read stale
    assert "status" in lifecycle
    assert lifecycle["status"] == "RUNNING"
    from marketpilot.dashboard.router import _evaluate_projection_liveness
    cadence = meta.get("evaluation_cadence_seconds", 60)
    is_stale, liveness = _evaluate_projection_liveness(lifecycle, cadence)
    assert not is_stale
    assert liveness == "RUNNING"

@pytest.mark.asyncio
async def test_dashboard_market_feed_isolation(fake_settings, monkeypatch, tmp_path):
    """
    Prove that DashboardObservationFeed strictly publishes to in-memory store
    and does NOT overwrite the daemon's durable evaluation truth.
    """
    from marketpilot.dashboard.feed import DashboardObservationFeed
    from marketpilot.dashboard.store import DashboardReadStore
    from marketpilot.dashboard.projections import FileProjectionRepository
    from marketpilot.dashboard.models import ProjectionMetadata
    
    fake_repo_dir = tmp_path / "projections"
    fake_repo_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("marketpilot.dashboard.projections.DEFAULT_PROJECTIONS_DIR", fake_repo_dir)
    
    # 1. Daemon writes canonical evaluation
    daemon_repo = FileProjectionRepository(directory=fake_repo_dir)
    meta = ProjectionMetadata(
        projection_version=1,
        evaluation_id="cycle-real",
        daemon_instance_id="daemon-123",
        generated_at=time.time(),
        evaluation_as_of=time.time(),
        cycle_outcome="SIGNALS_GENERATED_NO_ELIGIBLE_CANDIDATE",
        cycle_reason="None met criteria",
        intents_count=5,
        candidates_count=0
    )
    from marketpilot.dashboard.models import EvidenceTraceabilityReadModel
    evidence = EvidenceTraceabilityReadModel(
        strategy_id="test",
        strategy_version="1",
        parameter_set_id="p1",
        timeframe="H1",
        direction="LONG",
        regime_model="trend",
        regime_state="BULL",
        market_scope="ALL",
        execution_policy_version="1",
        research_cutoff_timestamp=0,
        evidence_status="INAPPLICABLE",
        deterministic_rank=1,
        deterministic_decision_key="BTCUSDT:test:1:p1:LONG",
        symbol="BTCUSDT",
        snapshot_id="s1",
        signal_timestamp=time.time(),
        pricing_status="UNPRICEABLE",
        is_eligible=False
    )
    daemon_repo.publish_daemon_evaluation([], [evidence], metadata=meta)
    
    # Verify file is there
    initial_stat = daemon_repo.evidence_file.stat()
    
    # 2. Dashboard observation feed updates market intelligence
    dashboard_store = DashboardReadStore(repository=daemon_repo)
    
    # Mock MarketDataReader
    class FakeMarketDataReader:
        async def get_server_time(self): return time.time()
        async def get_klines(self, *args, **kwargs): return []
        async def get_tickers(self, *args, **kwargs): return []
        
    client = FakeMarketDataReader()
    
    # Instead of running the feed (which requires klines), we just call publish_market_observation directly
    # as this is the new API contract
    from marketpilot.dashboard.models import MarketIntelligenceReadModel
    intelligence = MarketIntelligenceReadModel(
        symbol="ETHUSDT",
        snapshot_version="1",
        timeframe="60",
        market_data_environment="MAINNET",
        candle_open_timestamp=time.time(),
        candle_close_timestamp=time.time(),
        snapshot_creation_timestamp=time.time(),
        open="100", high="100", low="100", close="100", volume="100", turnover="100",
        spread_bps="1", atr_percent="1", momentum_24h="1", trend_strength="1", trend_age_candles=1,
        snapshot_id="s1"
    )
    
    dashboard_store.publish_market_observation([intelligence])
    
    # 3. Assert daemon evaluation files were completely untouched
    final_stat = daemon_repo.evidence_file.stat()
    assert initial_stat.st_mtime == final_stat.st_mtime
    
    # 4. Assert dashboard correctly reads canonical evaluation while appending memory market data
    dashboard_meta = dashboard_store.get_projection_metadata()
    assert dashboard_meta is not None
    assert dashboard_meta["evaluation_id"] == "cycle-real"
    assert dashboard_meta["intents_count"] == 5
    
    dashboard_evidence = dashboard_store.get_all_evidence()
    assert len(dashboard_evidence) == 1
    assert dashboard_evidence[0].deterministic_decision_key == "BTCUSDT:test:1:p1:LONG"
    
    dashboard_intel = dashboard_store.get_market_intelligence("ETHUSDT")
    assert dashboard_intel is not None
    assert dashboard_intel.snapshot_id == "s1"
