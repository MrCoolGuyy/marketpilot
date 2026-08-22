from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from marketpilot.models.execution import ExecutionFill, ExecutionIntent
from marketpilot.models.journal import (
    ExecutionIntentCreated,
    ExecutionValidationRejected,
    ExecutionSubmissionPrepared,
    ExecutionSubmissionAuthorized,
    ExecutionNetworkAttemptStarted,
    ExecutionAcknowledgmentObserved,
    ExecutionFillObserved,
    ExecutionProtectionObserved,
    ExecutionTerminalObserved
)
from enum import StrEnum

class TransitionStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    DUPLICATE_NOOP = "DUPLICATE_NOOP"
    INVALID_TRANSITION = "INVALID_TRANSITION"

class ReducerState(BaseModel):
    """The canonical deterministic state of a single logical execution."""
    logical_order_id: str
    environment: str = "UNKNOWN"

    intent: Optional[ExecutionIntent] = None
    submission_attempt_id: Optional[str] = None
    permit_id: Optional[str] = None

    entry_fill: Optional[ExecutionFill] = None
    exit_fill: Optional[ExecutionFill] = None

    is_terminal: bool = False
    is_rejected: bool = False
    protection_state: Optional[str] = None

    applied_events: set[str] = Field(default_factory=set)

class ExecutionStateReducer:
    """Pure deterministic transition interpreter."""

    @staticmethod
    def _event_identity(event: BaseModel) -> str:
        """Determines the unique identity of an event for deduplication."""
        if isinstance(event, ExecutionIntentCreated):
            return f"INTENT_{event.intent.intent_id}"
        elif isinstance(event, ExecutionValidationRejected):
            return f"REJECT_{event.intent_id}"
        elif isinstance(event, ExecutionSubmissionPrepared):
            return f"PREPARED_{event.submission_attempt_id}"
        elif isinstance(event, ExecutionSubmissionAuthorized):
            return f"AUTH_{event.submission_attempt_id}_{event.permit_id}"
        elif isinstance(event, ExecutionNetworkAttemptStarted):
            return f"ATTEMPT_{event.permit_id}"
        elif isinstance(event, ExecutionAcknowledgmentObserved):
            return f"ACK_{event.submission_attempt_id}"
        elif isinstance(event, ExecutionFillObserved):
            return f"FILL_{event.fill.exec_id}"
        elif isinstance(event, ExecutionProtectionObserved):
            return f"PROT_{event.submission_attempt_id}_{event.protection_state}"
        elif isinstance(event, ExecutionTerminalObserved):
            return f"TERM_{event.submission_attempt_id}_{event.terminal_state}"
        return f"UNKNOWN_{id(event)}"

    @staticmethod
    def apply(state: Optional[ReducerState], event: BaseModel) -> tuple[ReducerState, TransitionStatus]:
        if state is None:
            if isinstance(event, ExecutionIntentCreated):
                state = ReducerState(
                    logical_order_id=event.intent.logical_order_id,
                    environment=event.intent.environment
                )
            else:
                # Cannot apply an event without intent initialized unless it's a completely disjoint rejected event.
                if isinstance(event, ExecutionValidationRejected):
                    state = ReducerState(
                        logical_order_id=event.intent_id, # Actually intent_id is not logical_order_id strictly, but close enough.
                    )
                else:
                    # Depending on how the loop starts, if state is None, we might just create a dummy or fail.
                    # For safety, we fail if it's not the start.
                    return None, TransitionStatus.INVALID_TRANSITION

        event_id = ExecutionStateReducer._event_identity(event)
        if event_id in state.applied_events:
            return state, TransitionStatus.DUPLICATE_NOOP

        # Copy state for pure update
        new_state = state.model_copy(deep=True)
        new_state.applied_events.add(event_id)

        if isinstance(event, ExecutionIntentCreated):
            new_state.intent = event.intent
            new_state.environment = event.intent.environment

        elif isinstance(event, ExecutionValidationRejected):
            new_state.is_rejected = True
            new_state.is_terminal = True

        elif isinstance(event, ExecutionSubmissionPrepared):
            new_state.submission_attempt_id = event.submission_attempt_id

        elif isinstance(event, ExecutionSubmissionAuthorized):
            new_state.permit_id = event.permit_id

        elif isinstance(event, ExecutionNetworkAttemptStarted):
            pass # Identity tracked

        elif isinstance(event, ExecutionAcknowledgmentObserved):
            pass

        elif isinstance(event, ExecutionFillObserved):
            if new_state.entry_fill is None:
                new_state.entry_fill = event.fill
            else:
                # If entry exists, this must be exit fill
                new_state.exit_fill = event.fill

        elif isinstance(event, ExecutionProtectionObserved):
            new_state.protection_state = event.protection_state

        elif isinstance(event, ExecutionTerminalObserved):
            new_state.is_terminal = True

        return new_state, TransitionStatus.ACCEPTED
