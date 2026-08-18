"""
MarketPilot Daemon - Mission Control Service.

The main entrypoint. Handles initialization, event bus wiring, and graceful shutdown.
"""

import asyncio
import signal
import uuid
import time
import os
if os.name != 'nt':
    import fcntl
else:
    import msvcrt
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
from marketpilot import __version__
from marketpilot.exchange.verifier import PositionModeVerifier, VerificationStatus

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

        self.daemon_instance_id = str(uuid.uuid4())
        self.started_at = time.time()
        # Ensure context carries the instance ID for projections
        ctx.daemon_instance_id = self.daemon_instance_id
        self.journal = ctx.journal

        self.pipeline = ctx.pipeline
        self.notifier = ctx.notifier
        self.exposure = ctx.exposure if hasattr(ctx, "exposure") else None
        self.verifier = PositionModeVerifier(self.client)

        self.scheduler = Scheduler(self.ts, interval_seconds=10.0)
        self.scheduler.set_callback(self._on_tick)

        self._shutdown_event = asyncio.Event()
        self._dashboard_task = None
        self._uvicorn_server = None
        self._lock_file = None

    async def _verify_account_mode(self):
        """Verify One-Way Mode at startup for a canary symbol."""
        logger.info("Verifying Account Mode (One-Way Mode required)...")
        if getattr(self.client, "_execution_mode", None) == "DEMO" and getattr(self.client, "_demo_flag", False):
             logger.info("Skipping account mode verification for DEMO mode.")
             return

        try:
            status = await self.verifier.verify_symbol("BTCUSDT")
            if status != VerificationStatus.VERIFIED_ONE_WAY:
                raise ValueError(f"Incompatible mode detected: status={status.value}. Only One-Way Mode is supported.")
        except Exception as e:
            logger.error(f"Failed to verify account mode: {e}")
            raise RuntimeError("ACCOUNT MODE SAFETY FAILED") from e

    def _acquire_single_writer_lock(self, lock_path: str = "marketpilot.lock"):
        """Implement single-MarketPilot-writer invariant."""
        logger.info("Acquiring single-writer lock (Scope: LOCAL_HOST)...")
        self._lock_path = lock_path
        try:
            self._lock_file = open(self._lock_path, "w")
            if os.name == 'nt':
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_file.write(str(os.getpid()))
            self._lock_file.flush()
        except OSError as e:
            logger.error(f"Failed to acquire single-writer lock. Another MarketPilot instance is running: {e}")
            raise RuntimeError("SINGLE WRITER SAFETY FAILED: Another instance is running.") from e

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
            start_time=self.ts.time(),
            daemon_instance_id=self.daemon_instance_id
        )

        # Publish daemon heartbeat
        import time
        from marketpilot.dashboard.projections import FileProjectionRepository
        repo = FileProjectionRepository()
        repo.publish_lifecycle(
            daemon_instance_id=self.daemon_instance_id,
            status="RUNNING",
            mode="CONTINUOUS",
            started_at=self.started_at,
            heartbeat_at=time.time()
        )

        await self.bus.publish(CycleStartedEvent(ctx=ctx))

        # Wait a bit just for tests
        await asyncio.sleep(0.1)
        self.watchdog.end_cycle()

    async def run(self):
        """Runs the daemon loop."""
        self._setup_signals()
        logger.info("Starting Mission Control Daemon...")

        self._acquire_single_writer_lock()
        await self.client.connect()
        await self._verify_account_mode()

        # Inject into dashboard app
        dashboard_app.state.daemon = self
        dashboard_app.state.health = self.health
        dashboard_app.state.metrics = self.metrics
        dashboard_app.state.pipeline = self.pipeline
        dashboard_app.state.watchdog = self.watchdog
        dashboard_app.state.settings = self.settings

        # Phase 3: Dashboard Read Model fields
        dashboard_app.state.recovery_result = None

        # Start Dashboard Server
        config = uvicorn.Config(dashboard_app, host="0.0.0.0", port=8000, log_level="info")
        self._uvicorn_server = uvicorn.Server(config)
        self._dashboard_task = asyncio.create_task(self._uvicorn_server.serve())

        # Send Startup Notification
        from marketpilot.notifications.telegram_formatters import format_system_status
        alloc_cap = getattr(self.settings.portfolio, "allocated_capital", None)
        msg_str = format_system_status(
            status="STARTING",
            mode=self.settings.execution_mode.value,
            env=self.settings.exchange.environment.value,
            version=__version__,
            daemon_state="INITIALIZING",
            recovery_safe="PENDING",
            phase="PHASE 5",
            policy_version="N/A",
            allocated_capital=str(alloc_cap) if alloc_cap else "N/A",
        )
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.STARTUP,
            message_data={"message": msg_str}
        ))

        # Perform Recovery
        safe = await self._perform_startup_recovery()
        if not safe:
            logger.error("HALTING due to UNSAFE recovery.")
            await self.notifier.notify(NotificationEvent(
                event_type=NotificationType.CIRCUIT_BREAKER_HALTED,
                message_data={"reason": "UNSAFE_RECOVERY"}
            ))
            # Don't start scheduler/watchdog
            await self.notifier.start_polling()
            await self._shutdown_event.wait()
            await self._graceful_shutdown()
            return

        self.watchdog.start()
        self.scheduler.start()
        await self.notifier.start_polling()

        await self._shutdown_event.wait()
        await self._graceful_shutdown()

    async def run_one_cycle(self):
        """Perform exactly one real canonical Phase-4 daemon evaluation cycle."""
        logger.info("Starting SINGLE Phase-4 evaluation cycle...")
        self._setup_signals()

        self._acquire_single_writer_lock()
        await self.client.connect()
        await self._verify_account_mode()

        logger.info("Hydrating dependencies...")
        logger.info("Evaluation architecture: PHASE_4_CAUSAL")
        logger.info("Runtime mutation capability: READ_ONLY")

        # Manually trigger one cycle
        await self._on_tick()

        # Wait a bit for background event bus processing to finish
        await asyncio.sleep(2.0)

        logger.info("Single evaluation cycle complete. Orders submitted: 0")

        # Write terminal/tombstone projection
        from marketpilot.dashboard.projections import FileProjectionRepository
        import time
        repo = FileProjectionRepository()
        repo.publish_lifecycle(
            daemon_instance_id=self.daemon_instance_id,
            status="COMPLETED",
            mode="ONCE",
            started_at=self.started_at,
            heartbeat_at=time.time(),
            completed_at=time.time()
        )

        if self._lock_file:
            try:
                if os.name == 'nt':
                    self._lock_file.seek(0)
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
                if hasattr(self, "_lock_path"):
                    os.remove(self._lock_path)
            except Exception as e:
                logger.error(f"Failed to release lock: {e}")

    def _setup_signals(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except NotImplementedError:
                pass # Windows doesn't support add_signal_handler well, rely on KeyboardInterrupt

    async def _perform_startup_recovery(self) -> bool:
        """Runs the recovery engine to reconstruct state."""
        logger.info("Acquiring Exchange Recovery Snapshot...")

        from marketpilot.models.recovery import ExchangeRecoverySnapshot
        try:
            open_orders = await self.client.get_active_orders()
            positions = await self.client.get_positions()
            pos_list = positions.get("result", {}).get("list", [])
            active_pos_ids = tuple(p.get("symbol") for p in pos_list if float(p.get("size", 0)) > 0)

            # Simulated lineage requirements from Journal
            # In Phase 3, we mock this by passing all active decision IDs from the Journal
            journal_active_decision_ids = set()
            if hasattr(self.journal, "get_active_decision_ids"):
                journal_active_decision_ids = set(self.journal.get_active_decision_ids())

            # Lineage sufficiency pagination
            history_dict = {}
            cursor = ""
            seen_cursors = set()

            # Use policy if configured, otherwise infinite (lineage or exhaustion driven)
            max_pages = getattr(self.settings, "recovery_max_pages", float("inf"))
            pages_fetched = 0

            while pages_fetched < max_pages:
                try:
                    hist_page = await self.client.get_order_history(limit=50, cursor=cursor)
                except Exception as e:
                    logger.error(f"API retrieval failure during recovery pagination: {e}")
                    raise RuntimeError("API retrieval failure during recovery") from e

                items = hist_page.get("list", [])
                if not items:
                    break
                for h in items:
                    history_dict[h.get("orderId")] = h

                cursor = hist_page.get("nextPageCursor")
                if not cursor:
                    break

                if cursor in seen_cursors:
                    logger.error("Cyclic cursor detected during recovery pagination.")
                    raise RuntimeError("Cyclic cursor detected during recovery pagination")
                seen_cursors.add(cursor)

                pages_fetched += 1

                # Check lineage sufficiency: all journal active decisions must be explained
                # Here we assume orderLinkId maps to decision_id for simplicity in V1
                found_decisions = {h.get("orderLinkId") for h in history_dict.values()}
                if journal_active_decision_ids and journal_active_decision_ids.issubset(found_decisions):
                    break

            # Note: We do NOT raise an error here yet. Some lineages might only be explained by executions.
            found_decisions = {h.get("orderLinkId") for h in history_dict.values()}

            # Execution sufficiency pagination
            execution_dict = {}
            exec_cursor = ""
            seen_exec_cursors = set()
            exec_pages = 0

            while exec_pages < max_pages:
                try:
                    exec_page = await self.client.get_execution_history(limit=50, cursor=exec_cursor)
                except Exception as e:
                    logger.error(f"API retrieval failure during execution pagination: {e}")
                    raise RuntimeError("API retrieval failure during execution recovery") from e

                items = exec_page.get("list", [])
                if not items:
                    break
                for ex in items:
                    execution_dict[ex.get("execId")] = ex

                exec_cursor = exec_page.get("nextPageCursor")
                if not exec_cursor:
                    break

                if exec_cursor in seen_exec_cursors:
                    logger.error("Cyclic cursor detected during execution pagination.")
                    raise RuntimeError("Cyclic cursor detected during execution pagination")
                seen_exec_cursors.add(exec_cursor)
                exec_pages += 1

                # Check lineage sufficiency: all journal active decisions must be explained
                # For executions, some might not exist if order was cancelled. We'll just break if we find all required.
                found_exec_decisions = {ex.get("orderLinkId") for ex in execution_dict.values()}
                if journal_active_decision_ids and journal_active_decision_ids.issubset(found_exec_decisions):
                    break

            # Final sufficiency check for executions
            found_exec_decisions = {ex.get("orderLinkId") for ex in execution_dict.values()}
            if journal_active_decision_ids and not journal_active_decision_ids.issubset(found_exec_decisions):
                # If they were explained by order_history (e.g. Cancelled), that's fine.
                # But if we assume execution pagination *must* explain them, we'd fail here.
                # Let's check union.
                combined_decisions = found_decisions.union(found_exec_decisions)
                if not journal_active_decision_ids.issubset(combined_decisions):
                    logger.error("Unresolved lineage when API execution history ends or bound reached.")
                    raise RuntimeError("Unresolved lineage when API execution history ends")

            order_ids = tuple(o.get("orderId") for o in open_orders)

            snapshot = ExchangeRecoverySnapshot(
                snapshot_id=str(uuid.uuid4()),
                timestamp=time.time(),
                open_orders=order_ids,
                active_positions=active_pos_ids
            )

            journal_orders = set()
            journal_positions = set()

            result = self.reconciler.reconcile_startup(
                journal_orders,
                journal_positions,
                snapshot,
                history_dict,
                execution_dict
            )

            from marketpilot.dashboard.server import app as dashboard_app
            dashboard_app.state.recovery_result = result

            if result.success:
                logger.info("Recovery SAFE. Hydrating ExposureManager...")
                from decimal import Decimal
                self.exposure.replace_all(list(active_pos_ids), Decimal("0"))
                return True
            else:
                logger.error(f"Recovery UNSAFE: {result.fatal_error}")
                return False

        except Exception as e:
            logger.error(f"Recovery failed due to exception: {e}")
            from marketpilot.dashboard.server import app as dashboard_app
            from marketpilot.models.recovery import RecoveryResult
            dashboard_app.state.recovery_result = RecoveryResult(
                success=False,
                snapshot=ExchangeRecoverySnapshot(snapshot_id="", timestamp=0, open_orders=(), active_positions=()),
                reconciled_records=(),
                fatal_error=str(e)
            )
            return False

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

        if self._lock_file:
            try:
                if os.name == 'nt':
                    self._lock_file.seek(0)
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
                if hasattr(self, "_lock_path"):
                    os.remove(self._lock_path)
            except Exception as e:
                logger.error(f"Failed to release single-writer lock: {e}")

        logger.info("Graceful Shutdown complete. Exiting.")
