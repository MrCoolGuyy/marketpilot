"""
MarketPilot Core - Mission Control Factory.

Central Dependency Injection for the Engine Layer.
Ensures both Daemon and CLI share the exact same runtime graph.
"""
from dataclasses import dataclass
from typing import Any

from loguru import logger

from marketpilot.config.settings import AppSettings
from marketpilot.core.time_source import SystemClock
from marketpilot.core.event_bus import EventBus
from marketpilot.core.metrics_registry import MetricsRegistry

from marketpilot.engines.circuit_breaker import CircuitBreaker
from marketpilot.engines.health_monitor import HealthMonitor
from marketpilot.engines.watchdog import Watchdog
from marketpilot.engines.trading_pipeline import TradingPipeline

from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.engines.scanner_engine import ScannerEngine
from marketpilot.engines.indicator_engine import IndicatorEngine
from marketpilot.engines.regime_engine import RegimeEngine
from marketpilot.engines.strategy_engine import StrategyEngine
from marketpilot.engines.risk_engine import RiskEngine
from marketpilot.engines.decision_audit_engine import DecisionAuditEngine
from marketpilot.engines.execution_engine import ExecutionEngine
from marketpilot.engines.reconciler_engine import ReconcilerEngine
from marketpilot.engines.journal_engine import JournalEngine

from marketpilot.exchange.market_data_fetcher import MarketDataFetcher
from marketpilot.scanner.snapshot_builder import InstrumentSnapshotBuilder
from marketpilot.notifications.telegram_notifier import TelegramNotifier
@dataclass(slots=True)
class RuntimeContext:
    """Strongly typed dependency container for the MarketPilot runtime."""
    settings: AppSettings
    ts: SystemClock
    bus: EventBus
    metrics: MetricsRegistry
    cb: CircuitBreaker
    health: HealthMonitor
    watchdog: Watchdog
    
    client: BybitClient
    market_data_fetcher: MarketDataFetcher
    snapshot_builder: InstrumentSnapshotBuilder
    scanner: ScannerEngine
    indicator: IndicatorEngine
    regime: RegimeEngine
    strategy: StrategyEngine
    risk: RiskEngine
    audit: DecisionAuditEngine
    execution: ExecutionEngine
    reconciler: ReconcilerEngine
    journal: JournalEngine
    
    notifier: TelegramNotifier
    pipeline: TradingPipeline
    
    # Optional Validation Service (if Phase 11 implemented)
    validation: Any = None


class MissionControlFactory:
    """Modular factory to build and validate the dependency graph."""
    
    @classmethod
    def build_core(cls, settings: AppSettings) -> dict:
        ts = SystemClock()
        bus = EventBus()
        metrics = MetricsRegistry()
        cb = CircuitBreaker()
        health = HealthMonitor(metrics, cb)
        watchdog = Watchdog(ts, cb)
        return {
            "ts": ts,
            "bus": bus,
            "metrics": metrics,
            "cb": cb,
            "health": health,
            "watchdog": watchdog,
        }
        
    @classmethod
    def build_exchange(cls, settings: AppSettings) -> dict:
        client = BybitClient(settings.exchange)
        return {"client": client}
        
    @classmethod
    def build_market_data(cls, exchange: dict) -> dict:
        fetcher = MarketDataFetcher(exchange["client"])
        return {"market_data_fetcher": fetcher}
        
    @classmethod
    def build_engines(cls, settings: AppSettings, core: dict, exchange: dict) -> dict:
        scanner = ScannerEngine(settings.scanner)
        indicator = IndicatorEngine(settings.indicators)
        regime = RegimeEngine()
        strategy = StrategyEngine(settings.strategy)
        risk = RiskEngine(settings.risk)
        audit = DecisionAuditEngine()
        execution = ExecutionEngine(exchange["client"], core["cb"])
        reconciler = ReconcilerEngine()
        journal = JournalEngine()
        
        builder = InstrumentSnapshotBuilder(indicator)
        
        return {
            "snapshot_builder": builder,
            "scanner": scanner,
            "indicator": indicator,
            "regime": regime,
            "strategy": strategy,
            "risk": risk,
            "audit": audit,
            "execution": execution,
            "reconciler": reconciler,
            "journal": journal,
        }
        
    @classmethod
    def build_notifications(cls, settings: AppSettings) -> TelegramNotifier:
        return TelegramNotifier(settings.telegram)
        
    @classmethod
    def build_runtime(cls, settings: AppSettings | None = None) -> RuntimeContext:
        """Builds the complete dependency graph and validates it."""
        if settings is None:
            settings = AppSettings()
            
        core = cls.build_core(settings)
        exchange = cls.build_exchange(settings)
        market_data = cls.build_market_data(exchange)
        engines = cls.build_engines(settings, core, exchange)
        notifier = cls.build_notifications(settings)
        
        ctx = RuntimeContext(
            settings=settings,
            ts=core["ts"],
            bus=core["bus"],
            metrics=core["metrics"],
            cb=core["cb"],
            health=core["health"],
            watchdog=core["watchdog"],
            client=exchange["client"],
            market_data_fetcher=market_data["market_data_fetcher"],
            snapshot_builder=engines["snapshot_builder"],
            scanner=engines["scanner"],
            indicator=engines["indicator"],
            regime=engines["regime"],
            strategy=engines["strategy"],
            risk=engines["risk"],
            audit=engines["audit"],
            execution=engines["execution"],
            reconciler=engines["reconciler"],
            journal=engines["journal"],
            notifier=notifier,
            pipeline=None  # type: ignore
        )
        
        pipeline = TradingPipeline(ctx)
        
        # Patch the context with the created pipeline (cyclic reference)
        object.__setattr__(ctx, "pipeline", pipeline)
        
        cls._validate_dependencies(ctx)
        return ctx
        
    @classmethod
    def _validate_dependencies(cls, ctx: RuntimeContext) -> None:
        """Ensures no engine is None before the runtime is returned."""
        for field_name in ctx.__slots__:
            if field_name == "validation":
                continue # Optional
            val = getattr(ctx, field_name)
            if val is None:
                logger.error(f"MissionControlFactory Validation Failed: {field_name} is None")
                raise RuntimeError(f"Dependency Injection Error: {field_name} failed to instantiate.")
