import pytest
import os
from unittest.mock import MagicMock, AsyncMock, patch

from marketpilot.daemon.service import MissionControlDaemon
from marketpilot.config.settings import AppSettings
        
def test_single_writer_lock(tmp_path):
    lock_path = tmp_path / "marketpilot.lock"
    settings = AppSettings()
    
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        mock_build.return_value = ctx
        
        daemon = MissionControlDaemon()
        
        # Mock the OS locking call to simulate a held lock
        if os.name == 'nt':
            mock_target = "marketpilot.daemon.service.msvcrt.locking"
        else:
            mock_target = "marketpilot.daemon.service.fcntl.flock"
            
        with patch(mock_target, side_effect=OSError("Lock held by another process")):
            with pytest.raises(RuntimeError, match="SINGLE WRITER SAFETY FAILED"):
                daemon._acquire_single_writer_lock(lock_path=str(lock_path))
    
@pytest.mark.asyncio
async def test_verify_account_mode_success():
    settings = AppSettings()
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        
        client = AsyncMock()
        ctx.client = client
        mock_build.return_value = ctx
        
        daemon = MissionControlDaemon()
        daemon.verifier = AsyncMock()
        from marketpilot.exchange.verifier import VerificationStatus
        daemon.verifier.verify_symbol.return_value = VerificationStatus.VERIFIED_ONE_WAY
        
        await daemon._verify_account_mode() # Should pass without raising
        
@pytest.mark.asyncio
async def test_verify_account_mode_failure():
    settings = AppSettings()
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        
        client = AsyncMock()
        ctx.client = client
        mock_build.return_value = ctx
        
        daemon = MissionControlDaemon()
        daemon.verifier = AsyncMock()
        from marketpilot.exchange.verifier import VerificationStatus
        daemon.verifier.verify_symbol.return_value = VerificationStatus.INCOMPATIBLE_HEDGE
        
        with pytest.raises(RuntimeError, match="ACCOUNT MODE SAFETY FAILED"):
            await daemon._verify_account_mode()

@pytest.mark.asyncio
async def test_daemon_startup_gating():
    settings = AppSettings()
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        
        client = AsyncMock()
        client.get_active_orders = AsyncMock(return_value=[{"orderId": "order-1"}]) # Orphan
        client.get_positions = AsyncMock(return_value={"result": {"list": []}})
        client.get_order_history = AsyncMock(return_value=[])
        ctx.client = client
        
        reconciler = MagicMock()
        from marketpilot.models.recovery import RecoveryResult, ExchangeRecoverySnapshot, ReconciliationRecord
        unsafe_result = RecoveryResult(
            success=False,
            snapshot=ExchangeRecoverySnapshot(snapshot_id="1", timestamp=0, open_orders=("order-1",), active_positions=()),
            reconciled_records=(
                ReconciliationRecord(record_id="1", timestamp=0, issue_type="EXCHANGE_ORPHAN", resolution_action="MANUAL_INTERVENTION_REQUIRED"),
            ),
            fatal_error="Unsafe"
        )
        reconciler.reconcile_startup.return_value = unsafe_result
        ctx.reconciler = reconciler
        
        notifier = AsyncMock()
        ctx.notifier = notifier
        
        mock_build.return_value = ctx
        
        daemon = MissionControlDaemon()
        daemon.verifier = AsyncMock()
        from marketpilot.exchange.verifier import VerificationStatus
        daemon.verifier.verify_symbol.return_value = VerificationStatus.VERIFIED_ONE_WAY
        daemon._shutdown_event = AsyncMock() # to not block
        daemon._graceful_shutdown = AsyncMock()
        daemon.watchdog = MagicMock()
        daemon.scheduler = MagicMock()
        
        # We manually bypass the _on_tick/scheduler for this test
        with patch("marketpilot.dashboard.server.app") as mock_app:
            await daemon.run() # Should not raise, but should halt
            
            daemon.scheduler.start.assert_not_called()
            daemon.watchdog.start.assert_not_called()
            daemon._graceful_shutdown.assert_called_once()

