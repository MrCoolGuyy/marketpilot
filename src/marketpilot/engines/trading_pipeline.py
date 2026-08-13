"""
MarketPilot Engines - Trading Pipeline.

A thin orchestrator. Contains NO trading logic.
Uses Dependency Injection to wire up engines to the Event Bus.
"""

import time
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from marketpilot.core.factory import RuntimeContext

from marketpilot.engines.scanner_engine import ScannerEngine
from marketpilot.engines.indicator_engine import IndicatorEngine
from marketpilot.engines.regime_engine import RegimeEngine
from marketpilot.engines.strategy_engine import StrategyEngine
from marketpilot.engines.risk_engine import RiskEngine
from marketpilot.engines.decision_audit_engine import DecisionAuditEngine
from marketpilot.engines.execution_engine import ExecutionEngine
from marketpilot.engines.reconciler_engine import ReconcilerEngine
from marketpilot.engines.journal_engine import JournalEngine

from marketpilot.core.event_bus import EventBus
from marketpilot.core.metrics_registry import MetricsRegistry
from marketpilot.models.events import (
    CycleStartedEvent,
    ScannerFinishedEvent,
    IndicatorsFinishedEvent,
    RegimeFinishedEvent,
    StrategyFinishedEvent,
    RiskFinishedEvent,
    ExecutionCompletedEvent,
    ReconciliationCompletedEvent,
    JournalCompletedEvent,
    CycleFinishedEvent
)

class TradingPipeline:
    """Coordinates events between engines without knowing their internal logic."""
    
    def __init__(self, ctx: 'RuntimeContext'):
        self.ctx = ctx
        self.bus = ctx.bus
        self.metrics = ctx.metrics
        
        self.market_data_fetcher = ctx.market_data_fetcher
        self.snapshot_builder = ctx.snapshot_builder
        
        self.scanner = ctx.scanner
        self.indicator = ctx.indicator
        self.regime = ctx.regime
        self.strategy = ctx.strategy
        self.risk = ctx.risk
        self.audit = ctx.audit
        self.execution = ctx.execution
        self.reconciler = ctx.reconciler
        self.journal = ctx.journal
        
        self._subscribe_all()
        
    def _subscribe_all(self):
        """Wire up the event bus to the engines."""
        self.bus.subscribe(CycleStartedEvent, self._on_cycle_started)
        self.bus.subscribe(ScannerFinishedEvent, self._on_scanner_finished)
        self.bus.subscribe(IndicatorsFinishedEvent, self._on_indicators_finished)
        self.bus.subscribe(RegimeFinishedEvent, self._on_regime_finished)
        self.bus.subscribe(StrategyFinishedEvent, self._on_strategy_finished)
        self.bus.subscribe(RiskFinishedEvent, self._on_risk_finished)
        self.bus.subscribe(ExecutionCompletedEvent, self._on_execution_completed)
        self.bus.subscribe(ReconciliationCompletedEvent, self._on_reconciliation_completed)
        self.bus.subscribe(JournalCompletedEvent, self._on_journal_completed)
        
    async def _on_cycle_started(self, event: CycleStartedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Scanner starting...")
        
        try:
            # 1. Fetch top candidates from market data
            limit = self.ctx.settings.scanner.max_results
            quote_coin = self.ctx.settings.scanner.quote_coin
            min_turnover = self.ctx.settings.scanner.min_turnover_24h
            
            raw_candidates = await self.market_data_fetcher.fetch_scan_candidates(
                quote_coin=quote_coin,
                min_turnover_24h=min_turnover,
                limit=limit
            )
            
            # 2. Build domain snapshots
            snapshots = []
            for raw in raw_candidates:
                snap = self.snapshot_builder.build(raw)
                snapshots.append(snap)
                
            # 3. Engine evaluation
            scanner_result = self.scanner.evaluate(snapshots)
        except Exception as e:
            logger.error(f"Cycle {event.ctx.cycle_id}: Scanner failed: {e}")
            from marketpilot.models.scanner import ScannerResult
            scanner_result = ScannerResult(top_candidates=[], market_health=0, timestamp=time.time())
        
        self.metrics.record_latency("scanner_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(ScannerFinishedEvent(ctx=event.ctx, scanner_result=scanner_result))
        
    async def _on_scanner_finished(self, event: ScannerFinishedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Calculating indicators...")
        indicators = {}
        for snap in event.scanner_result.top_candidates:
            indicators[snap.symbol] = self.indicator.calculate([]) # Pass raw klines
            
        self.metrics.record_latency("indicator_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(IndicatorsFinishedEvent(ctx=event.ctx, scanner_result=event.scanner_result, indicators=indicators))
        
    async def _on_indicators_finished(self, event: IndicatorsFinishedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Determining market regime...")
        regimes = {}
        for snap in event.scanner_result.top_candidates:
            regimes[snap.symbol] = self.regime.determine_regime(snap, event.indicators.get(snap.symbol))
            
        self.metrics.record_latency("regime_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(RegimeFinishedEvent(ctx=event.ctx, scanner_result=event.scanner_result, indicators=event.indicators, regimes=regimes))
        
    async def _on_regime_finished(self, event: RegimeFinishedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Evaluating strategy...")
        
        # We need to evaluate strategy for each symbol and collect results
        strategy_results = []
        for snap in event.scanner_result.top_candidates:
            # Assuming strategy.evaluate returns a StrategyResult
            # In Phase 3, it evaluates against all strategies. 
            # We mock the return value in tests anyway.
            res = self.strategy.evaluate_all(snap, event.indicators.get(snap.symbol), event.regimes.get(snap.symbol))
            if isinstance(res, list):
                strategy_results.extend(res)
            else:
                strategy_results.append(res)
            
        self.metrics.record_latency("strategy_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(StrategyFinishedEvent(ctx=event.ctx, scanner_result=event.scanner_result, regimes=event.regimes, strategy_results=strategy_results))
        
    async def _on_strategy_finished(self, event: StrategyFinishedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Applying risk controls...")
        trade_plan = self.risk.evaluate(event.strategy_results, event.regimes)
        self.metrics.record_latency("risk_engine", (time.time() - start) * 1000)
        
        if trade_plan:
            self.audit.audit_decision(event.ctx.decision_id, trade_plan)
            await self.bus.publish(RiskFinishedEvent(ctx=event.ctx, trade_plan=trade_plan))
        else:
            logger.info(f"Cycle {event.ctx.cycle_id}: No trade generated.")
            await self.bus.publish(CycleFinishedEvent(ctx=event.ctx))
            
    async def _on_risk_finished(self, event: RiskFinishedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Executing trade...")
        result = await self.execution.execute(event.trade_plan)
        self.metrics.record_latency("execution_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(ExecutionCompletedEvent(ctx=event.ctx, trade_plan=event.trade_plan, execution_result=result))
        
    async def _on_execution_completed(self, event: ExecutionCompletedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Reconciling execution...")
        report = self.reconciler.reconcile(event.trade_plan, event.execution_result)
        self.metrics.record_latency("reconciler_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(ReconciliationCompletedEvent(
            ctx=event.ctx,
            trade_plan=event.trade_plan,
            execution_result=event.execution_result,
            report=report
        ))
        
    async def _on_reconciliation_completed(self, event: ReconciliationCompletedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Journaling trade...")
        self.journal.commit_record(event.ctx.decision_id)
        self.metrics.record_latency("journal_engine", (time.time() - start) * 1000)
        
        await self.bus.publish(JournalCompletedEvent(ctx=event.ctx))
        
    async def _on_journal_completed(self, event: JournalCompletedEvent):
        logger.info(f"Cycle {event.ctx.cycle_id}: Cycle fully completed.")
        await self.bus.publish(CycleFinishedEvent(ctx=event.ctx))
