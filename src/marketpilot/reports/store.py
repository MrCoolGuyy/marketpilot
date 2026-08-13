"""
MarketPilot Reports — Local report store.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Generic, TypeVar, Optional, Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from marketpilot.models.backtest import BacktestResult
from marketpilot.models.optimization import OptimizationResult

T = TypeVar("T", bound=BaseModel)

class ReportEnvelope(BaseModel, Generic[T]):
    """Envelope for serialized reports."""
    schema_version: int = 1
    generated_at: datetime
    payload: T


class ReportStore:
    """Stores reports to local JSON files atomically."""

    def __init__(self, data_dir: str | Path = "data/reports") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _save_atomic(self, filename: str, data: str) -> None:
        """Save data to filename atomically."""
        target_path = self.data_dir / filename
        temp_path = self.data_dir / f"{filename}.{uuid4().hex}.tmp"
        
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(data)
            # Atomic rename (overwrites if exists on POSIX, on Windows os.replace does the same)
            os.replace(temp_path, target_path)
        finally:
            if temp_path.exists():
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def save_backtest(self, result: BacktestResult) -> None:
        """Save a backtest result."""
        envelope = ReportEnvelope(
            generated_at=datetime.now(tz=UTC),
            payload=result
        )
        
        # Pydantic's model_dump_json(round_trip=True) or default might convert Decimal to float.
        # We can dump to dict in json mode to let it convert Decimal to string/float depending on config.
        # But to be strictly deterministic and avoid float, we can configure Decimal serialization?
        # In pydantic v2, we can just use `model_dump_json()` and by default it often uses string/float.
        # However, to guarantee strings, let's just let it do its default behavior, but we will test it.
        data = envelope.model_dump_json()
        self._save_atomic("backtest.latest.json", data)

    def load_backtest(self) -> Optional[BacktestResult]:
        """Load the latest backtest result."""
        target_path = self.data_dir / "backtest.latest.json"
        if not target_path.exists():
            return None
            
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Pydantic will parse it back
            envelope = ReportEnvelope[BacktestResult].model_validate(data)
            return envelope.payload
        except (json.JSONDecodeError, ValidationError, OSError):
            return None

    def save_optimization(self, result: OptimizationResult) -> None:
        """Save an optimization result."""
        envelope = ReportEnvelope(
            generated_at=datetime.now(tz=UTC),
            payload=result
        )
        data = envelope.model_dump_json()
        self._save_atomic("optimization.latest.json", data)

    def load_optimization(self) -> Optional[OptimizationResult]:
        """Load the latest optimization result."""
        target_path = self.data_dir / "optimization.latest.json"
        if not target_path.exists():
            return None
            
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            envelope = ReportEnvelope[OptimizationResult].model_validate(data)
            return envelope.payload
        except (json.JSONDecodeError, ValidationError, OSError):
            return None
