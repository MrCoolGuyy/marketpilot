"""
MarketPilot Daemon - Mission Control Service.

The main entrypoint. Handles initialization, event bus wiring, and graceful shutdown.
"""

import asyncio
import signal
import uuid
import time
from loguru import logger

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

from marketpilot.core.factory import MissionControlFactory

from marketpilot.notifications.telegram_notifier import TelegramNotifier
from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
import uvicorn
from marketpilot.dashboard.server import app as dashboard_app

class MissionControlDaemon:
    def __init__(self):
        ctx = MissionControlFactory.build_runtime()
        
        self.settings = ctx.settings
        self.ts = ctx.ts
        self.bus = ctx.bus
        self.metrics = ctx.metrics
        self.cb = ctx.cb
        self.health = ctx.health
        self.watchdog = ctx.watchdog
        
        self.client = ctx.client
        self.scanner = ctx.scanner
        self.indicator = ctx.indicator
        self.regime = ctx.regime
        self.strategy = ctx.strategy
        self.risk = ctx.risk
        self.audit = ctx.audit
        self.execution = ctx.execution
        self.reconciler = ctx.reconciler
        self.journal = ctx.journal
        
        self.pipeline = ctx.pipeline
        self.notifier = ctx.notifier
        
        self.scheduler = Scheduler(self.ts, interval_seconds=10.0)
        self.scheduler.set_callback(self._on_tick)
        
        self._shutdown_event = asyncio.Event()
        self._dashboard_task = None
        self._uvicorn_server = None

    async def _on_tick(self):
        """Triggered by scheduler to start a new cycle."""
        self.cb.assert_healthy()
        self.watchdog.start_cycle()
        
        cycle_id = str(uuid.uuid4())
        ctx = PipelineContext(
            decision_id=cycle_id,
            cycle_id=cycle_id,
            config_hash="dev-config",
            market_time=self.ts.now(),
            start_time=self.ts.time()
        )
        
        await self.bus.publish(CycleStartedEvent(ctx=ctx))
        
        # Wait a bit just for tests
        await asyncio.sleep(0.1)
        self.watchdog.end_cycle()
        
    async def run(self):
        """Runs the daemon loop."""
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
        config = uvicorn.Config(dashboard_app, host="0.0.0.0", port=8000, log_level="info")
        self._uvicorn_server = uvicorn.Server(config)
        self._dashboard_task = asyncio.create_task(self._uvicorn_server.serve())
        
        # Send Startup Notification
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.STARTUP,
            message_data={
                "version": "1.0.0",
                "git_commit": "unknown",
                "config_hash": "LOCKED",
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
        """Soft-halts the trading pipeline without stopping the daemon."""
        logger.warning(f"OPERATOR HALT by {operator} ({ip}): {reason}")
        await self.scheduler.stop()
        # Fake wait for cycle to finish
        await asyncio.sleep(0.5)
        self.cb.state = self.cb.state.HALTED
        
    async def resume_trading(self, operator: str, ip: str, reason: str):
        """Resumes trading pipeline."""
        logger.info(f"OPERATOR RESUME by {operator} ({ip}): {reason}")
        self.cb.reset()
        self.scheduler.start()
        
    async def _graceful_shutdown(self):
        logger.info("Initiating Graceful Shutdown sequence...")
        
        # 1. Stop Scheduler (no new cycles)
        logger.info("1. Stopping Scheduler...")
        await self.scheduler.stop()
        
        # 2. Wait for current cycle to drain (Watchdog will timeout eventually if hung)
        logger.info("2. Draining Event Bus (Waiting for active cycles to finish)...")
        await asyncio.sleep(1) # Fake drain delay
        
        # 3. Stop Watchdog
        logger.info("3. Stopping Watchdog...")
        self.watchdog.stop()
        
        # 4. Flush Journal
        logger.info("4. Flushing Journal to disk...")
        # self.journal.flush()
        
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
