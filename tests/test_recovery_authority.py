import pytest
import tempfile
import json
from pathlib import Path
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from marketpilot.engines.recovery_engine import RecoveryEngine
from marketpilot.engines.journal_engine import JournalEngine
from marketpilot.engines.exposure_manager import ExposureManager
from marketpilot.engines.position_manager import PositionManager

@pytest.mark.asyncio
async def test_recovery_authority_separation():
    """
    Test that RecoveryEngine preserves the authority model:
    - ALLOCATION_COMMITTED without exchange position -> RESERVED
    - ALLOCATION_COMMITTED with matching exchange position -> ACTIVE
    - Actual exchange position without matching journal -> STATE_MISMATCH (Unsafe)
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        journal_path = Path(tmp_dir) / "test_events.jsonl"
        journal_engine = JournalEngine(log_dir=tmp_dir)
        journal_engine.events_path = journal_path

        # 1. Write journal entries
        with open(journal_path, "w") as f:
            f.write(json.dumps({
                "type": "AllocationCommitted",
                "allocation_id": "BTCUSDT:alloc_1",
                "lineage_identity": "lin_1",
                "risk_amount": "100.0",
                "timestamp": 1000.0
            }) + "\n")

            f.write(json.dumps({
                "type": "AllocationCommitted",
                "allocation_id": "ETHUSDT:alloc_2",
                "lineage_identity": "lin_2",
                "risk_amount": "200.0",
                "timestamp": 1000.0
            }) + "\n")

        exposure_manager = ExposureManager()

        # Scenario 1: Exchange only knows about ETHUSDT
        mock_client = MagicMock()
        mock_client.get_positions = AsyncMock(return_value={
            "result": {
                "list": [
                    {"symbol": "ETHUSDT", "size": "1", "markPrice": "3000"}
                ]
            }
        })

        engine = RecoveryEngine(
            client=mock_client,
            position_manager=PositionManager(),
            journal_engine=journal_engine,
            exposure_manager=exposure_manager
        )

        result = await engine.run_recovery()
        assert result.is_safe is True

        snap = exposure_manager.snapshot()
        assert snap.active_risk_amount == Decimal("200.0")
        assert snap.reserved_risk_amount == Decimal("100.0")
        assert "ETHUSDT" in snap.active_position_ids
        assert "BTCUSDT:alloc_1" in snap.reserved_allocation_ids

        # Scenario 2: Exchange has an unknown position (SOLUSDT)
        mock_client_unsafe = MagicMock()
        mock_client_unsafe.get_positions = AsyncMock(return_value={
            "result": {
                "list": [
                    {"symbol": "ETHUSDT", "size": "1", "markPrice": "3000"},
                    {"symbol": "SOLUSDT", "size": "10", "markPrice": "150"}
                ]
            }
        })
        engine_unsafe = RecoveryEngine(
            client=mock_client_unsafe,
            position_manager=PositionManager(),
            journal_engine=journal_engine,
            exposure_manager=exposure_manager
        )

        result_unsafe = await engine_unsafe.run_recovery()
        assert result_unsafe.is_safe is False
        assert any("SOLUSDT" in reason and "STATE_MISMATCH" in reason for reason in result_unsafe.reasons)
