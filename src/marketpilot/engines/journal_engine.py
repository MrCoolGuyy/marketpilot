"""
MarketPilot Engines - Journal Engine.

Maintains an event journal for lifecycle events, and an analytics journal for performance.
Emits the final TradeExecutionRecord.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from marketpilot.models.journal import TradeExecutionRecord
from marketpilot.models.position import PositionEvent

class JournalEngine:
    """Persists the final trade execution records."""
    
    def __init__(self, log_dir: str = "logs/journal"):
        self.log_dir = Path(log_dir)
        self.events_path = self.log_dir / "events.jsonl"
        self.analytics_path = self.log_dir / "analytics.jsonl"
        self.records_path = self.log_dir / "records.jsonl"
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
    def append_event(self, event: PositionEvent) -> None:
        """Appends a single lifecycle event immediately."""
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")
            
    def commit_record(self, record: TradeExecutionRecord) -> None:
        """Commits the final TradeExecutionRecord (usually upon Exited event)."""
        with open(self.records_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")
            
        if record.analytics:
            with open(self.analytics_path, "a", encoding="utf-8") as f:
                f.write(record.analytics.model_dump_json() + "\n")

