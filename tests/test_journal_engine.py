import pytest
import os
from decimal import Decimal
from unittest.mock import patch, mock_open

from marketpilot.engines.journal_engine import JournalEngine
from marketpilot.models.journal import SubmissionPrepared
from marketpilot.models.submission import PreparedSubmission

def test_journal_engine_append_durable_event(tmp_path):
    journal = JournalEngine(log_dir=str(tmp_path))
    
    event = SubmissionPrepared(
        submission=PreparedSubmission(
            submission_id="SUB-1",
            allocation_id="ALLOC-1",
            client_order_id="CLIENT-1",
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty="1.0",
            price="50000",
            stop_loss="49000",
            take_profit="52000"
        )
    )
    
    journal.append_durable_event(event)
    
    # Verify file was written
    with open(journal.events_path, "r") as f:
        lines = f.readlines()
        assert len(lines) == 1
        assert "SUB-1" in lines[0]

@patch("os.fsync")
def test_journal_engine_append_durable_event_fsync_failure(mock_fsync, tmp_path):
    mock_fsync.side_effect = OSError("Disk full or I/O error")
    
    journal = JournalEngine(log_dir=str(tmp_path))
    
    event = SubmissionPrepared(
        submission=PreparedSubmission(
            submission_id="SUB-1",
            allocation_id="ALLOC-1",
            client_order_id="CLIENT-1",
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty="1.0",
            price="50000",
            stop_loss="49000",
            take_profit="52000"
        )
    )
    
    with pytest.raises(RuntimeError) as exc_info:
        journal.append_durable_event(event)
        
    assert "Failed to durably commit event" in str(exc_info.value)
    assert "Disk full" in str(exc_info.value)
