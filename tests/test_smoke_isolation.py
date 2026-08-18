import asyncio
import os
import tempfile
import pytest
import subprocess
import hashlib
from pathlib import Path

def test_smoke_test_isolation():
    """
    Ensure scripts/smoke_test_phase5.py uses an isolated state
    and does NOT modify the canonical production journal.
    """
    # 1. Capture state before
    prod_journal_dir = Path("logs/journal")

    # Optional: we can track the exact file contents if the directory exists
    before_files = {}
    if prod_journal_dir.exists():
        for f in prod_journal_dir.glob("*.jsonl"):
            with open(f, "rb") as fd:
                before_files[f.name] = hashlib.sha256(fd.read()).hexdigest()

    # 2. Run the smoke test
    result = subprocess.run(
        ["uv", "run", "python", "scripts/smoke_test_phase5.py"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent.parent)
    )

    # 3. Verify it passed
    assert result.returncode == 0, f"Smoke test failed: {result.stderr}"
    assert "PHASE 5 SMOKE TEST COMPLETED" in result.stderr or "PHASE 5 SMOKE TEST COMPLETED" in result.stdout
    assert "NETWORK PERMITS = 0" in result.stderr or "NETWORK PERMITS = 0" in result.stdout
    assert "EXCHANGE ORDERS = 0" in result.stderr or "EXCHANGE ORDERS = 0" in result.stdout

    # 4. Verify canonical isolation
    after_files = {}
    if prod_journal_dir.exists():
        for f in prod_journal_dir.glob("*.jsonl"):
            with open(f, "rb") as fd:
                after_files[f.name] = hashlib.sha256(fd.read()).hexdigest()

    assert before_files == after_files, "Smoke test modified canonical production journal state!"

    # 5. Look for stray test_journal.jsonl in current dir
    assert not Path("test_journal.jsonl").exists(), "Smoke test leaked test_journal.jsonl into workspace root!"
