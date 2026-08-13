"""
MarketPilot Engines � Decision Audit Engine.

Acts as the black box flight recorder for the bot.
Saves detailed JSONL for ML, and readable Markdown for humans.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from marketpilot.models.audit import AuditRecord

class DecisionAuditEngine:
    """Logs AuditRecords in both machine-readable and human-readable formats."""

    def __init__(self, log_dir: str = "logs/audit"):
        self.log_dir = Path(log_dir)
        self.jsonl_path = self.log_dir / "audit.jsonl"
        self.md_dir = self.log_dir / "markdown"
        
        # Ensure directories exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.md_dir.mkdir(parents=True, exist_ok=True)

    def _generate_markdown(self, record: AuditRecord) -> str:
        """Generates a human-readable summary of the decision."""
        lines = []
        lines.append(f"# Audit Report: {record.decision_id}")
        lines.append(f"**Symbol**: {record.market_snapshot.symbol}")
        lines.append(f"**Timestamp**: {record.timestamp}")
        lines.append(f"**Config Hash**: {record.config_hash}")
        lines.append("")
        
        lines.append("## Scanner")
        lines.append(f"- **Market Quality**: {record.market_snapshot.market_quality}")
        for k, v in record.market_snapshot.score_breakdown.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
            
        lines.append("## Regime")
        lines.append(f"**{record.regime_snapshot.value}**")
        lines.append("")
        
        lines.append("## Feature Vector")
        for k, v in record.feature_vector.items():
            lines.append(f"- **{k}**: {v}")
        lines.append("")
        
        lines.append("## Strategy")
        for res in record.strategy_results:
            lines.append(f"### {res.strategy_name}")
            lines.append(f"- **Signal**: {res.signal.value}")
            lines.append(f"- **Confidence**: {res.confidence}")
            lines.append(f"- **Reason**: {res.reason_code}")
            if res.is_actionable and res.candidate_trade:
                lines.append(f"- **Expected RR**: {res.candidate_trade.expected_rr}")
        lines.append("")
        
        lines.append("## Risk")
        if record.risk_result:
            status = "PASS" if record.risk_result.approved else "REJECT"
            lines.append(f"- **Status**: {status}")
            lines.append(f"- **Reason**: {record.risk_result.reason}")
            if record.risk_result.approved:
                lines.append(f"- **RR**: {record.risk_result.rr}")
                lines.append(f"- **Position Size**: {record.risk_result.position_size}")
        else:
            lines.append("- No trade proposed by strategies.")
        lines.append("")
        
        lines.append("## Validation & Execution")
        if record.validation_passed is not None:
            val_status = "PASS" if record.validation_passed else "FAIL"
            lines.append(f"- **Validation**: {val_status}")
            lines.append(f"- **Validation Reason**: {record.validation_reason}")
        
        if record.execution_submitted:
            lines.append("- **Execution**: Submitted")
        else:
            lines.append("- **Execution**: Not Submitted")
            
        lines.append("")
        lines.append(f"*Pipeline Processing Time: {record.total_processing_time_ms:.2f} ms*")
        
        return "\n".join(lines)

    def log(self, record: AuditRecord) -> None:
        """Persists the audit record."""
        # Write JSONL
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            # Pydantic model_dump_json handles serialization
            f.write(record.model_dump_json() + "\n")
            
        # Write Markdown
        md_content = self._generate_markdown(record)
        md_file = self.md_dir / f"{record.decision_id}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)
