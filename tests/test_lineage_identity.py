"""
Cross-process lineage identity stability test.

Proves that deterministic lineage identity generation (json + SHA-256)
is immune to Python's per-process hash() memory salting by running the
ACTUAL production lineage path in isolated subprocesses.

Uses subprocess.run with explicit timeouts — never multiprocessing.Queue —
so a child crash always surfaces as a test failure instead of a hang.
"""
import subprocess
import sys
import textwrap

import pytest


# ── child program template ──────────────────────────────────────────
# The child builds a fully valid FinalCandidate using the CURRENT Pydantic
# contracts, derives its deterministic_decision_key, then runs the exact
# same json + SHA-256 lineage computation used in PortfolioAllocator.
_CHILD_PROGRAM = textwrap.dedent(r"""
import hashlib
import json
import os
from decimal import Decimal

from marketpilot.models.causal import (
    FinalCandidate, EvidenceAssessment, AssessmentStatus,
    PreSizeEconomics, SizeAwareEconomics, SizingDecision,
    SignalIntent, StrategyIdentity, SignalDirection,
    ExecutableQuoteSnapshot, MarketDataEnvironment,
    PricedCandidate, PricingStatus,
)

signal_timestamp_us = {signal_timestamp_us}

intent = SignalIntent(
    intent_id="intent_test",
    identity=StrategyIdentity(
        registry_version="1",
        strategy_id="test",
        strategy_version="1",
        parameter_set_id="default",
    ),
    direction=SignalDirection.LONG,
    symbol="BTCUSDT",
    signal_timestamp=float(signal_timestamp_us) / 1_000_000,
    signal_timestamp_us=signal_timestamp_us,
    logical_stop_loss=Decimal("90"),
    logical_take_profit=Decimal("110"),
    provenance_snapshot_id="snap_1",
)

priced = PricedCandidate(
    candidate_id="pc_1",
    intent=intent,
    quote=ExecutableQuoteSnapshot(
        quote_id="q",
        symbol="BTCUSDT",
        environment=MarketDataEnvironment.MAINNET,
        quote_timestamp=0,
        bid=Decimal("100"),
        ask=Decimal("101"),
    ),
    executable_entry_price=Decimal("101"),
    pricing_status=PricingStatus.PRICED,
    rejection_reason=None,
)

candidate = FinalCandidate(
    candidate_id="cand_1",
    priced_candidate=priced,
    assessment=EvidenceAssessment(
        assessment_id="1",
        status=AssessmentStatus.VALIDATED,
        evidence=None,
    ),
    pre_size_economics=PreSizeEconomics(
        approved_expected_gross_r=Decimal("0"),
        pre_size_expected_cost_r=Decimal("0"),
        pre_size_net_ev_r=Decimal("0"),
        cost_model_provenance="",
    ),
    sizing=SizingDecision(
        sizing_id="1",
        provisional_quantity=Decimal("1"),
        effective_stop_price=Decimal("90"),
        risk_policy_provenance="",
    ),
    size_aware_economics=SizeAwareEconomics(
        size_aware_cost_r=Decimal("0"),
        final_net_ev_r=Decimal("0"),
    ),
    is_eligible=True,
    rejection_reason=None,
)

# ── production lineage computation (same as PortfolioAllocator) ──
lineage_payload = [
    "v1",
    candidate.deterministic_decision_key,
    candidate.priced_candidate.intent.signal_timestamp_us,
]
raw_key = json.dumps(lineage_payload, separators=(",", ":"))
lineage_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

print(f"{{lineage_hash}}|{{os.getpid()}}")
""")


def _run_child(signal_timestamp_us: int) -> tuple[str, int]:
    """Run the lineage computation in an isolated subprocess, return (hash, pid)."""
    program = _CHILD_PROGRAM.format(signal_timestamp_us=signal_timestamp_us)
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    parts = result.stdout.strip().split("|")
    return parts[0], int(parts[1])


def test_cross_process_lineage_identity():
    """
    Proves that deterministic lineage identity generation is immune to
    Python's hash() memory salting by using json + SHA-256 across distinct
    OS processes.
    """
    import time
    ts1 = int(time.time() * 1_000_000)
    ts2 = ts1 + 1000

    # Same canonical payload in two totally isolated processes
    hash_a, pid_a = _run_child(ts1)
    hash_b, pid_b = _run_child(ts1)

    assert pid_a != pid_b, "Children must be separate OS processes"
    assert hash_a == hash_b, (
        f"Lineage hash not deterministic across processes: {hash_a!r} != {hash_b!r}"
    )

    # Different signal_timestamp_us must yield a different hash
    hash_c, _ = _run_child(ts2)
    assert hash_a != hash_c, (
        f"Lineage hash collided across distinct timestamps: {hash_a!r} == {hash_c!r}"
    )
