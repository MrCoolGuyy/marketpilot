"""MarketPilot Demo — Local store for audit trail."""

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from marketpilot.models.demo import DemoOrderRecord

class DemoAuditEnvelope(BaseModel):
    records: list[DemoOrderRecord]
    
class DemoAuditStore:
    """Stores demo execution records to local JSON file atomically."""

    def __init__(self, data_dir: str | Path = "data/reports") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.data_dir / "demo_audit_trail.json"
        
    def _save_atomic(self, data: str) -> None:
        temp_path = self.data_dir / f"demo_audit_trail.json.{uuid4().hex}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(temp_path, self.journal_path)
        finally:
            if temp_path.exists():
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def load_records(self) -> list[DemoOrderRecord]:
        if not self.journal_path.exists():
            return []
            
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            envelope = DemoAuditEnvelope.model_validate(data)
            return envelope.records
        except (json.JSONDecodeError, ValidationError, OSError):
            return []
            
    def save_records(self, records: list[DemoOrderRecord]) -> None:
        envelope = DemoAuditEnvelope(records=records)
        data = envelope.model_dump_json()
        self._save_atomic(data)
