"""
MarketPilot Dashboard - Projections Repository.

Provides a durable file-based repository for cross-process communication
between the canonical Phase-4 daemon (writer) and the dashboard (reader).
"""
import json
import os
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import TypeAdapter

from marketpilot.dashboard.models import MarketIntelligenceReadModel, EvidenceTraceabilityReadModel, ProjectionMetadata, ProjectionEnvelope
import time

# Use a default path in the workspace or home directory for projections
DEFAULT_PROJECTIONS_DIR = Path(".marketpilot/projections")

class FileProjectionRepository:
    """
    Durable JSON file store for dashboard read models.
    Provides atomic writes to ensure readers never see partial state.
    """
    def __init__(self, directory: Optional[Path] = None):
        self.directory = directory or DEFAULT_PROJECTIONS_DIR
        self.intelligence_file = self.directory / "market_intelligence.json"
        self.evidence_file = self.directory / "evidence_traceability.json"
        self.lifecycle_file = self.directory / "daemon_lifecycle.json"
        
        # Ensure directory exists
        self.directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize files if they don't exist
        empty_metadata = ProjectionMetadata(
            projection_version=1,
            evaluation_id="init",
            daemon_instance_id="init",
            generated_at=time.time(),
            evaluation_as_of=time.time()
        ).model_dump(mode="json")
        empty_envelope = {"metadata": empty_metadata, "data": {}}
        if not self.intelligence_file.exists():
            self._write_atomic(self.intelligence_file, empty_envelope)
        if not self.evidence_file.exists():
            self._write_atomic(self.evidence_file, empty_envelope)

    def _write_atomic(self, file_path: Path, data: dict):
        """Write JSON atomically using a temporary file and atomic rename."""
        temp_path = file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Failed to atomic-write {file_path}: {e}")
            if temp_path.exists():
                os.remove(temp_path)
                
    def _read_safe_envelope(self, file_path: Path) -> dict:
        """Read JSON safely. Returns the full envelope."""
        try:
            if not file_path.exists():
                return {}
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Legacy artifact rejection
            meta = data.get("metadata", {})
            if meta.get("schema_version") != "1.0" or meta.get("projection_version") != 1:
                logger.warning(f"Legacy or unsupported projection ignored: {file_path}")
                return {}
                
            return data
        except Exception as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return {}

    def _read_safe_data(self, file_path: Path) -> dict:
        """Read JSON safely and extract the data payload."""
        envelope = self._read_safe_envelope(file_path)
        return envelope.get("data", envelope)

    def publish_daemon_evaluation(self, intelligence: list[MarketIntelligenceReadModel], evidence: list[EvidenceTraceabilityReadModel], metadata: ProjectionMetadata):
        """Publish observations. The daemon uses this to project canonical evaluation state."""
        meta_dict = metadata.model_dump(mode="json")
        
        if intelligence is not None:
            new_intelligence = {}
            for model in intelligence:
                new_intelligence[model.symbol] = model.model_dump(mode="json")
            self._write_atomic(self.intelligence_file, {"metadata": meta_dict, "data": new_intelligence})
            
        if evidence is not None:
            new_evidence = {}
            for model in evidence:
                if model.deterministic_decision_key:
                    new_evidence[model.deterministic_decision_key] = model.model_dump(mode="json")
            self._write_atomic(self.evidence_file, {"metadata": meta_dict, "data": new_evidence})

    def get_market_intelligence(self, symbol: str) -> Optional[MarketIntelligenceReadModel]:
        """Read side: Get intelligence for a symbol."""
        data = self._read_safe_data(self.intelligence_file)
        model_data = data.get(symbol)
        if model_data:
            return MarketIntelligenceReadModel.model_validate(model_data)
        return None
        
    def get_evidence_traceability(self, decision_key: str) -> Optional[EvidenceTraceabilityReadModel]:
        """Read side: Get evidence for a decision key."""
        data = self._read_safe_data(self.evidence_file)
        model_data = data.get(decision_key)
        if model_data:
            return EvidenceTraceabilityReadModel.model_validate(model_data)
        return None
        
    def get_all_evidence(self) -> list[EvidenceTraceabilityReadModel]:
        """Read side: Get all evidence."""
        data = self._read_safe_data(self.evidence_file)
        adapter = TypeAdapter(list[EvidenceTraceabilityReadModel])
        return adapter.validate_python(list(data.values()))
        
    def publish_lifecycle(self, daemon_instance_id: str, status: str, mode: str, started_at: float, heartbeat_at: float, completed_at: Optional[float] = None):
        from marketpilot.dashboard.models import DaemonLifecycleProjection
        model = DaemonLifecycleProjection(
            daemon_instance_id=daemon_instance_id,
            status=status,
            mode=mode,
            started_at=started_at,
            heartbeat_at=heartbeat_at,
            completed_at=completed_at
        )
        self._write_atomic(self.lifecycle_file, {"metadata": {}, "data": model.model_dump(mode="json")})
        
    def get_lifecycle(self) -> Optional[dict]:
        """Read side: Get daemon lifecycle."""
        try:
            if not self.lifecycle_file.exists():
                return None
            with open(self.lifecycle_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("data")
        except Exception as e:
            logger.error(f"Failed to read {self.lifecycle_file}: {e}")
            return None
