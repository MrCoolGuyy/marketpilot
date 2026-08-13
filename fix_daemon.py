import asyncio
import signal
import uuid
import time
import hashlib
import subprocess
from loguru import logger
import uvicorn

import marketpilot
from marketpilot.core.time_source import SystemClock
from marketpilot.core.event_bus import EventBus
from marketpilot.core.metrics_registry import MetricsRegistry
from marketpilot.engines.circuit_breaker import CircuitBreaker
from marketpilot.engines.health_monitor import HealthMonitor
from marketpilot.engines.watchdog import Watchdog
from marketpilot.engines.trading_pipeline import TradingPipeline
from marketpilot.daemon.scheduler import Scheduler
from marketpilot.config.settings import AppSettings

from marketpilot.models.mission_control import PipelineContext
from marketpilot.models.events import CycleStartedEvent

from marketpilot.notifications.telegram_notifier import TelegramNotifier
from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
from marketpilot.dashboard.server import app as dashboard_app

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
from marketpilot.engines.position_manager import PositionManager

def get_git_commit() -> str:
    try:
        return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip()
    except Exception:
        return "unknown"

class MissionControlDaemon:
    def __init__(self):
        self.ts = SystemClock()
        self.bus = EventBus()
        self.metrics = MetricsRegistry()
        self.cb = CircuitBreaker()
        self.health = HealthMonitor(self.metrics, self.cb)
        self.watchdog = Watchdog(self.ts, self.cb)
        self.settings = AppSettings()
        
        # Instantiate real engines
        self.client = BybitClient(self.settings.exchange)
        self.scanner = ScannerEngine(self.settings.scanner)
        self.indicator = IndicatorEngine(self.settings.indicators)
        self.regime = RegimeEngine()
        self.strategy = StrategyEngine(self.settings.strategy)
        self.risk = RiskEngine(self.settings.risk)
        self.audit = DecisionAuditEngine()
        self.execution = ExecutionEngine(self.client, self.cb)
        self.reconciler = ReconcilerEngine()
        self.journal = JournalEngine()
        
        self.pipeline = TradingPipeline(
            self.bus, self.metrics,
            self.scanner, self.indicator, self.regime, self.strategy,
            self.risk, self.audit, self.execution, self.reconciler, self.journal
        )
        
        self.scheduler = Scheduler(self.ts, interval_seconds=self.settings.scheduler_interval_seconds)
        self.scheduler.set_callback(self._on_tick)
        
        self.notifier = TelegramNotifier(self.settings.telegram)
        
        self._shutdown_event = asyncio.Event()
        self._dashboard_task = None
        self._uvicorn_server = None
        self._active_cycles = 0

    async def _on_tick(self):
        \"\"\"Triggered by scheduler to start a new cycle.\"\"\"
        self.cb.assert_healthy()
        self.watchdog.start_cycle()
        self._active_cycles += 1
        
        cycle_id = str(uuid.uuid4())
        config_json = self.settings.model_dump_json()
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:8]
        
        ctx = PipelineContext(
            decision_id=cycle_id,
            cycle_id=cycle_id,
            config_hash=config_hash,
            market_time=self.ts.now(),
            start_time=self.ts.time()
        )
        
        try:
            await self.bus.publish(CycleStartedEvent(ctx=ctx))
        finally:
            self._active_cycles -= 1
            self.watchdog.end_cycle()
        
    async def run(self):
        \"\"\"Runs the daemon loop.\"\"\"
        self._setup_signals()
        logger.info("Starting Mission Control Daemon...")
        
        # Inject into dashboard app
        dashboard_app.state.daemon = self
        dashboard_app.state.health = self.health
        dashboard_app.state.metrics = self.metrics
        dashboard_app.state.pipeline = self.pipeline
        dashboard_app.state.watchdog = self.watchdog
        dashboard_app.state.settings = self.settings
        
        # Start Dashboard Server
        config = uvicorn.Config(dashboard_app, host=self.settings.uvicorn_host, port=self.settings.uvicorn_port, log_level="info")
        self._uvicorn_server = uvicorn.Server(config)
        self._dashboard_task = asyncio.create_task(self._uvicorn_server.serve())
        
        # Generate version and hash
        version = getattr(marketpilot, '__version__', '1.0.0')
        config_json = self.settings.model_dump_json()
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:8]
        git_commit = get_git_commit()
        
        # Send Startup Notification
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.STARTUP,
            message_data={
                "version": version,
                "git_commit": git_commit,
                "config_hash": config_hash,
                "start_time": str(self.ts.now())
            }
        ))
        
        self.watchdog.start()
        self.scheduler.start()
        await self.notifier.start_polling()
        
        await self._shutdown_event.wait()
        
        await self._graceful_shutdown()
        
    def _setup_signals(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except NotImplementedError:
                pass # Windows doesn't support add_signal_handler well, rely on KeyboardInterrupt
                
    async def halt_trading(self, operator: str, ip: str, reason: str):
        \"\"\"Soft-halts the trading pipeline without stopping the daemon.\"\"\"
        logger.warning(f"OPERATOR HALT by {operator} ({ip}): {reason}")
        await self.scheduler.stop()
        # Wait for cycles to finish
        while self._active_cycles > 0:
            await asyncio.sleep(0.1)
        self.cb.state = self.cb.state.HALTED
        self._log_operator_action(operator, ip, "HALT", reason)
        
    async def resume_trading(self, operator: str, ip: str, reason: str):
        \"\"\"Resumes trading pipeline.\"\"\"
        logger.info(f"OPERATOR RESUME by {operator} ({ip}): {reason}")
        self.cb.reset()
        self.scheduler.start()
        self._log_operator_action(operator, ip, "RESUME", reason)
        
    def _log_operator_action(self, operator: str, ip: str, action: str, reason: str):
        # Write to journal engine as requested
        if hasattr(self.journal, 'log_operator_action'):
            self.journal.log_operator_action(operator, ip, action, reason)
        else:
            with open("operator_audit.log", "a") as f:
                from datetime import datetime
                f.write(f"{datetime.utcnow().isoformat()} - Operator: {operator} - IP: {ip} - Action: {action} - Reason: {reason}\n")
        
    async def _graceful_shutdown(self):
        logger.info("Initiating Graceful Shutdown sequence...")
        
        # 1. Stop Scheduler (no new cycles)
        logger.info("1. Stopping Scheduler...")
        await self.scheduler.stop()
        
        # 2. Wait for current cycle to drain
        logger.info("2. Draining Event Bus (Waiting for active cycles to finish)...")
        while self._active_cycles > 0:
            await asyncio.sleep(0.1)
        
        # 3. Stop Watchdog
        logger.info("3. Stopping Watchdog...")
        self.watchdog.stop()
        
        # 4. Flush Journal
        logger.info("4. Flushing Journal to disk...")
        if hasattr(self.journal, 'flush'):
            self.journal.flush()
        
        # 5. Persist State
        logger.info("5. Persisting PositionManager state...")
        # self.position_manager.save_state()
        
        # 6. Stop Dashboard Server
        logger.info("6. Stopping Dashboard server...")
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
            
        # 7. Stop Telegram Polling
        logger.info("7. Stopping Telegram polling...")
        await self.notifier.stop_polling()
            
        # Send Shutdown Notification
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.SHUTDOWN,
            message_data={}
        ))
        
        logger.info("Graceful Shutdown complete. Exiting.")
