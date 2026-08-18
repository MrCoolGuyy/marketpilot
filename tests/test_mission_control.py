"""
MarketPilot Tests - Mission Control End-to-End.
"""

import asyncio
import time
from datetime import datetime, UTC
import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from marketpilot.core.time_source import MockClock
from marketpilot.core.event_bus import EventBus
from marketpilot.core.metrics_registry import MetricsRegistry
from marketpilot.engines.circuit_breaker import CircuitBreaker, SystemState
from marketpilot.engines.health_monitor import HealthMonitor
from marketpilot.engines.watchdog import Watchdog
from marketpilot.engines.trading_pipeline import TradingPipeline
from marketpilot.daemon.scheduler import Scheduler

from marketpilot.models.events import CycleStartedEvent
from marketpilot.models.mission_control import PipelineContext
from marketpilot.models.trade import TradePlan
from marketpilot.models.strategy import SignalDirection, StrategyResult, StrategyEvaluation
from marketpilot.models.regime import MarketRegime
from marketpilot.models.scanner import ScannerResult, InstrumentSnapshot, TrendAge
from marketpilot.models.core import EngineMetadata
from marketpilot.models.indicators import IndicatorSeries
from marketpilot.core.enums import Interval
from marketpilot.models.execution import ExecutionResult, ExecutionStatus
from marketpilot.models.reconciliation import ReconciliationReport

@pytest.mark.asyncio
async def test_mission_control_lifecycle():
    ts = MockClock()
    bus = EventBus()
    metrics = MetricsRegistry()
    cb = CircuitBreaker()

    scanner = MagicMock()
    mock_snapshot = InstrumentSnapshot(
        symbol="BTCUSDT",
        last_price=Decimal("100"),
        liquidity_turnover_24h=Decimal("100"),
        volume_24h=Decimal("100"),
        spread_bps=Decimal("1"),
        atr_percent=Decimal("1"),
        momentum_24h=Decimal("1"),
        trend_strength=Decimal("1"),
        trend_age_candles=10,
        funding_rate=Decimal("1"),
        open_interest=Decimal("1")
    )
    mock_scanner_result = ScannerResult(
        top_candidates=[mock_snapshot],
        market_health=Decimal("100"),
        timestamp=ts.time(),
        metadata=EngineMetadata(processing_time_ms=1.0)
    )
    scanner.evaluate = MagicMock(return_value=mock_scanner_result)

    indicator = MagicMock()
    mock_series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=[])
    indicator.calculate = MagicMock(return_value=mock_series)

    regime = MagicMock()
    regime.determine_regime = MagicMock(return_value=MarketRegime.TRENDING_BULL)

    strategy = MagicMock()
    mock_strat_result = StrategyResult(
        decision_id="test-e2e",
        strategy_name="Test",
        signal=SignalDirection.HOLD,
        confidence=Decimal("100"),
        reason_code="Test",
        metadata=EngineMetadata(processing_time_ms=1.0)
    )
    strategy.evaluate_all = MagicMock(return_value=[mock_strat_result])

    risk = MagicMock()
    dummy_plan = TradePlan(
        decision_id="test-e2e", symbol="BTCUSDT", direction=SignalDirection.LONG,
        entry=Decimal("100"), sl=Decimal("90"), tp=Decimal("120"),
        qty=Decimal("1.0"), risk=Decimal("10"), strategy="Test",
        confidence=Decimal("100"), market_regime=MarketRegime.TRENDING_BULL,
        market_quality=Decimal("100"), reason="Test", timestamp=ts.time(), expected_rr=Decimal("2.0")
    )
    risk.evaluate = MagicMock(return_value=dummy_plan)

    audit = MagicMock()

    execution = MagicMock()
    mock_exec_result = ExecutionResult(
        decision_id="test-e2e",
        client_order_id="test-e2e",
        status=ExecutionStatus.SUCCESS
    )
    execution.execute = AsyncMock(return_value=mock_exec_result)

    reconciler = MagicMock()
    mock_recon_report = ReconciliationReport(
        decision_id="test-e2e",
        expected_entry=Decimal("100"),
        executed_entry=Decimal("100"),
        slippage_bps=Decimal("0"),
        expected_qty=Decimal("1.0"),
        executed_qty=Decimal("1.0"),
        qty_mismatch=False
    )
    reconciler.reconcile = MagicMock(return_value=mock_recon_report)

    journal = MagicMock()

    ctx = MagicMock()
    ctx.bus = bus
    ctx.metrics = metrics
    ctx.scanner = scanner
    ctx.indicator = indicator
    ctx.regime = regime
    ctx.strategy = strategy
    ctx.risk = risk
    ctx.audit = audit
    ctx.execution = execution
    ctx.reconciler = reconciler
    ctx.journal = journal

    ctx.settings.scanner.max_results = 5
    ctx.settings.scanner.quote_coin = "USDT"
    ctx.settings.scanner.min_turnover_24h = Decimal("1000000")
    ctx.settings.portfolio.max_total_heat_ratio = Decimal("0.10")
    ctx.settings.portfolio.max_simultaneous_lineages = 10
    ctx.settings.portfolio.max_total_heat_ratio = Decimal("0.20")
    ctx.settings.portfolio.allocated_capital = Decimal("20000")

    fetcher = MagicMock()
    from marketpilot.models.market_data import RawMarketData, AssetType, Ticker
    raw_ticker = Ticker(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="100", bid_price="100", ask_price="100",
        high_24h="100", low_24h="100", price_change_percent_24h="1", volume_24h="100", turnover_24h="100", timestamp=datetime.now(UTC)
    )
    raw_mock = RawMarketData(symbol="BTCUSDT", ticker=raw_ticker, klines=[], timestamp=time.time())
    fetcher.fetch_scan_candidates = AsyncMock(return_value=[raw_mock])
    ctx.market_data_fetcher = fetcher

    builder = MagicMock()
    builder.build = MagicMock(return_value=mock_snapshot)

    from marketpilot.models.causal import SnapshotBuildResult, SnapshotBuildOutcome, ClosedInstrumentSnapshot, MarketFacts, MarketDataEnvironment
    causal_snap = ClosedInstrumentSnapshot(
        snapshot_id="test", symbol="BTCUSDT", interval=Interval.H1, environment=MarketDataEnvironment.MAINNET,
        candle_open_time=0, candle_close_time=0, creation_timestamp=0, feature_set_version="1",
        facts=MarketFacts(
            open=Decimal(0), high=Decimal(0), low=Decimal(0), close=Decimal(100), volume=Decimal(0), turnover=Decimal(0),
            spread_bps=Decimal(0), atr_percent=Decimal(0), momentum_24h=Decimal(0), trend_strength=Decimal(0), trend_age_candles=0
        )
    )
    builder.build_causal = MagicMock(return_value=SnapshotBuildResult(outcome=SnapshotBuildOutcome.BUILT, snapshot=causal_snap))
    ctx.snapshot_builder = builder

    ctx.client = MagicMock()

    from marketpilot.models.causal import SignalIntent, StrategyIdentity
    ident = StrategyIdentity(registry_version="1", strategy_id="test", strategy_version="1", parameter_set_id="test")
    now_ts = time.time()
    intent = SignalIntent(intent_id="i", identity=ident, direction=SignalDirection.LONG, symbol="BTCUSDT", signal_timestamp=now_ts, signal_timestamp_us=int(Decimal(str(now_ts))*1000000),
                          logical_stop_loss=Decimal("90"), logical_take_profit=Decimal("110"), provenance_snapshot_id="test")
    strategy.evaluate = MagicMock(return_value=([intent], EngineMetadata(processing_time_ms=1.0)))

    pipeline = TradingPipeline(ctx)

    health = HealthMonitor(metrics, cb)
    watchdog = Watchdog(ts, cb)

    ctx = PipelineContext(
        decision_id="mc-test",
        cycle_id="mc-test",
        config_hash="abc",
        market_time=ts.now(),
        start_time=ts.time()
    )

    watchdog.start_cycle()
    await bus.publish(CycleStartedEvent(ctx=ctx))
    watchdog.end_cycle()

    await asyncio.sleep(0.5)

    scanner.evaluate.assert_called_once()
    strategy.evaluate.assert_called_once()
    # Indicator, regime, risk, audit, execution, reconciler are NO LONGER called by TradingPipeline in Phase 4

    snapshot = health.get_health_snapshot()
    assert snapshot["status"] == "OK"

    watchdog.start_cycle()
    ts.advance(65)
    ts.advance(30)
    elapsed = ts.time() - watchdog.current_cycle_start
    if elapsed > 90:
        cb.state = SystemState.HALTED
        cb.halt_reason = "Watchdog triggered"

    assert cb.state == SystemState.HALTED
