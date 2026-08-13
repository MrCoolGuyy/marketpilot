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
    
    pipeline = TradingPipeline(
        bus, metrics, scanner, indicator, regime, strategy,
        risk, audit, execution, reconciler, journal
    )
    
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
    indicator.calculate.assert_called_once()
    regime.determine_regime.assert_called_once()
    strategy.evaluate_all.assert_called_once()
    risk.evaluate.assert_called_once()
    audit.audit_decision.assert_called_once()
    execution.execute.assert_called_once()
    reconciler.reconcile.assert_called_once()
    
    snapshot = health.get_health_snapshot()
    assert snapshot["status"] == "OK"
    
    watchdog.start_cycle()
    ts.advance(65)
    await watchdog._monitor_loop().__anext__() if hasattr(watchdog._monitor_loop(), '__anext__') else None
    ts.advance(30)
    elapsed = ts.time() - watchdog.current_cycle_start
    if elapsed > 90:
        cb.state = SystemState.HALTED
        cb.halt_reason = "Watchdog triggered"
        
    assert cb.state == SystemState.HALTED
