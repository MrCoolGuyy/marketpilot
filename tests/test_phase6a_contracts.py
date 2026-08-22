"""Tests for Phase 6A Execution domain, policies, and contracts."""

import pytest
import hashlib
from decimal import Decimal
import json

from marketpilot.models.execution import (
    ExecutionIntent,
    ValidatedOrderSpec,
    NetworkPermit,
    PermitAction,
    SubmissionState,
    ProtectionState,
    FillState,
    ExecutionFill,
    QuarantineProjection,
)
from marketpilot.models.journal import (
    ExecutionIntentCreated,
    ExecutionSubmissionPrepared,
    ExecutionNetworkAttemptStarted,
)
from marketpilot.config.settings import ExecutionMode
from marketpilot.core.factory import MutationTransportFactory, Phase6LiveMutationDisabled
from marketpilot.engines.exposure_manager import ExposureManager


def test_execution_intent_immutability():
    intent = ExecutionIntent(
        intent_id="INT-1",
        allocation_token_id="ALLOC-1",
        logical_order_id="LOG-1",
        symbol="BTCUSDT",
        side="LONG",
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100.0"),
        effective_stop=Decimal("90.0"),
        take_profit=None,
        environment="PAPER",
    )

    with pytest.raises(Exception):
        # Pydantic frozen=True should prevent this
        intent.symbol = "ETHUSDT"


def test_deterministic_permit_identity():
    # If we have the same authorization inputs, the permit must be perfectly reconstructable.
    # In Phase 6A, we enforce this by making it a contract that developers generate the permit_id
    # deterministically from its fields, rather than uuid4.

    auth_event_id = "AUTH-123"
    submission_id = "SUB-123"
    spec_hash = "abc123hash"

    def generate_permit_id(attempt_id: str, spec_hash: str, action: str, env: str) -> str:
        payload = f"{attempt_id}_{spec_hash}_{action}_{env}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    permit_id_1 = generate_permit_id(submission_id, spec_hash, PermitAction.CREATE, "PAPER")
    permit_id_2 = generate_permit_id(submission_id, spec_hash, PermitAction.CREATE, "PAPER")

    assert permit_id_1 == permit_id_2

    permit_1 = NetworkPermit(
        permit_id=permit_id_1,
        submission_attempt_id=submission_id,
        logical_order_id="LOG-1",
        action=PermitAction.CREATE,
        environment="PAPER",
        symbol="BTCUSDT",
        validated_spec_hash=spec_hash,
        authorization_event_id=auth_event_id,
        issued_at=1000.0,
    )

    # Change action -> different permit_id
    permit_id_diff = generate_permit_id(submission_id, spec_hash, PermitAction.CANCEL, "PAPER")
    assert permit_id_1 != permit_id_diff


def test_live_hard_lock_rejection():
    # Structural check that LIVE raises Phase6LiveMutationDisabled
    with pytest.raises(
        Phase6LiveMutationDisabled, match="LIVE mutation is structurally disabled in Phase 6"
    ):
        MutationTransportFactory.build_transport(ExecutionMode.LIVE)

    # DEMO should just return None in Phase 6A (stubbed)
    assert MutationTransportFactory.build_transport(ExecutionMode.DEMO) is None


def test_journal_event_serialization():
    # Ensure our Phase 6A events can be serialized properly to JSON
    event = ExecutionNetworkAttemptStarted(permit_id="PERMIT-123", timestamp=123456.789)

    # pydantic model_dump_json should work seamlessly
    json_str = event.model_dump_json()
    assert "PERMIT-123" in json_str

    loaded = ExecutionNetworkAttemptStarted.model_validate_json(json_str)
    assert loaded.permit_id == "PERMIT-123"
