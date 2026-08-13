"""MarketPilot Research — Local store for research journal."""

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from marketpilot.models.research import ResearchObservation, ResearchReport

class JournalEnvelope(BaseModel):
    schema_version: int = 1
    generated_at: datetime
    observations: list[ResearchObservation]
    
class ResearchStore:
    """Stores research observations to local JSON files atomically."""

    def __init__(self, data_dir: str | Path = "data/reports") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.journal_path = self.data_dir / "research_journal.json"
        
    def _save_atomic(self, filename: str, data: str) -> None:
        target_path = self.data_dir / filename
        temp_path = self.data_dir / f"{filename}.{uuid4().hex}.tmp"
        
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(temp_path, target_path)
        finally:
            if temp_path.exists():
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def load_observations(self) -> list[ResearchObservation]:
        if not self.journal_path.exists():
            return []
            
        try:
            with open(self.journal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            envelope = JournalEnvelope.model_validate(data)
            return envelope.observations
        except (json.JSONDecodeError, ValidationError, OSError):
            return []
            
    def save_observations(self, observations: list[ResearchObservation]) -> None:
        envelope = JournalEnvelope(
            generated_at=datetime.now(tz=UTC),
            observations=observations
        )
        # Using model_dump_json for reliable Decimal serialization in Pydantic V2
        data = envelope.model_dump_json()
        self._save_atomic("research_journal.json", data)
        
    def load_report(self) -> Optional[ResearchReport]:
        target_path = self.data_dir / "research_report.latest.json"
        if not target_path.exists():
            return None
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ResearchReport.model_validate(data)
        except (json.JSONDecodeError, ValidationError, OSError):
            return None
            
    def save_report(self, report: ResearchReport) -> None:
        data = report.model_dump_json()
        self._save_atomic("research_report.latest.json", data)
