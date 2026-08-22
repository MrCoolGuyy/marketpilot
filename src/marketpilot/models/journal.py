"""
MarketPilot Models - Journal domain models.
"""

from __future__ import annotations

from typing import Optional, Tuple
from decimal import Decimal
from pydantic import BaseModel, Field

from marketpilot.models.trade import TradePlan
from marketpilot.models.execution import (
    ExecutionResult,
    ExecutionIntent,
    ValidatedOrderSpec,
    NetworkPermit,
    ExecutionFill,
    QuarantineProjection,
    EmergencyCloseIntent,
)
from marketpilot.models.reconciliation import ReconciliationReport
from marketpilot.models.portfolio import PortfolioSnapshot
from marketpilot.models.position import PositionEvent
from marketpilot.models.submission import PreparedSubmission, OrderEventKey
from marketpilot.models.causal import FinalCandidate


class EventJournalEntry(BaseModel, frozen=True):
    """A log of a single lifecycle event for a position."""

    event: PositionEvent


class AnalyticsJournalEntry(BaseModel, frozen=True):
    """Detailed post-trade analytics."""

    decision_id: str
    symbol: str

    pnl: Decimal = Field(default=Decimal("0"))
    mae: Decimal = Field(default=Decimal("0"), description="Maximum Adverse Excursion")
    mfe: Decimal = Field(default=Decimal("0"), description="Maximum Favorable Excursion")
    duration_seconds: float = Field(default=0.0)

    total_fees: Decimal = Field(default=Decimal("0"))
    total_slippage_bps: Decimal = Field(default=Decimal("0"))


class TradeExecutionRecord(BaseModel, frozen=True):
    """The final artifact representing a complete trade lifecycle from decision to exit."""

    decision_id: str
    symbol: str

    trade_plan: TradePlan
    execution_result: ExecutionResult
    reconciliation: ReconciliationReport

    events: list[PositionEvent] = Field(default_factory=list)
    analytics: Optional[AnalyticsJournalEntry] = Field(default=None)

    portfolio_snapshot: Optional[PortfolioSnapshot] = Field(default=None)


# --- Phase 1 Additive Immutable Journal Events ---


class SubmissionPrepared(BaseModel):
    model_config = {"frozen": True}
    submission: PreparedSubmission


class SubmissionStarted(BaseModel):
    model_config = {"frozen": True}
    permit: NetworkPermit


class SubmissionAcknowledged(BaseModel):
    model_config = {"frozen": True}
    permit_id: str
    order_event_key: OrderEventKey


class CandidateEvaluationObserved(BaseModel):
    model_config = {"frozen": True}
    decision_id: str
    candidate: FinalCandidate


class AllocationOutcomeObserved(BaseModel):
    model_config = {"frozen": True}
    decision_id: str
    allocation_id: Optional[str] = None
    accepted: bool
    rejection_reason: Optional[str] = None


class LineageOutcomeObserved(BaseModel):
    model_config = {"frozen": True}
    allocation_id: str
    mutation_id: str
    outcome: str


class ExecutionOutcomeObserved(BaseModel):
    model_config = {"frozen": True}
    mutation_id: str
    exchange_order_id: str
    filled_qty: Decimal
    avg_price: Decimal


class CounterfactualOutcomeObserved(BaseModel):
    model_config = {"frozen": True}
    decision_id: str
    simulated_outcome: str


# --- Phase 5 Durable Journal Events ---


class ReservationPrepared(BaseModel):
    """Event emitted when capital is prepared in memory but not yet committed."""

    model_config = {"frozen": True}
    type: str = Field(default="ReservationPrepared", frozen=True)
    allocation_id: str
    lineage_identity: str
    risk_amount: Decimal
    timestamp: float


class AllocationCommitted(BaseModel):
    """Event emitted when the intent is durably authorized and becomes a true active lineage."""

    model_config = {"frozen": True}
    type: str = Field(default="AllocationCommitted", frozen=True)
    allocation_id: str
    lineage_identity: str
    risk_amount: Decimal
    timestamp: float


class ReservationAborted(BaseModel):
    """Event emitted when a prepared reservation fails to durably commit or fails CAS."""

    model_config = {"frozen": True}
    type: str = Field(default="ReservationAborted", frozen=True)
    allocation_id: str
    timestamp: float
    reason: str


# --- Phase 6A Execution Journal Events ---


class ExecutionIntentCreated(BaseModel, frozen=True):
    intent: ExecutionIntent
    timestamp: float


class ExecutionValidationRejected(BaseModel, frozen=True):
    intent_id: str
    reason: str
    timestamp: float


class ExecutionSubmissionPrepared(BaseModel, frozen=True):
    intent_id: str
    spec: ValidatedOrderSpec
    submission_attempt_id: str
    timestamp: float


class ExecutionSubmissionAuthorized(BaseModel, frozen=True):
    submission_attempt_id: str
    authorization_event_id: str
    permit_id: str
    timestamp: float


class ExecutionNetworkAttemptStarted(BaseModel, frozen=True):
    permit_id: str
    timestamp: float


class ExecutionAcknowledgmentObserved(BaseModel, frozen=True):
    submission_attempt_id: str
    order_id: str
    timestamp: float


class ExecutionSubmissionUnknown(BaseModel, frozen=True):
    submission_attempt_id: str
    reason: str
    timestamp: float


class ExecutionFillObserved(BaseModel, frozen=True):
    submission_attempt_id: str
    fill: ExecutionFill


class ExecutionTerminalObserved(BaseModel, frozen=True):
    submission_attempt_id: str
    terminal_state: str  # FILLED, CANCELED, REJECTED, etc.
    timestamp: float


class ExecutionProtectionObserved(BaseModel, frozen=True):
    submission_attempt_id: str
    protection_state: str  # CONFIRMED, MISMATCH, UNSAFE
    timestamp: float


class ExecutionAbsenceConfirmed(BaseModel, frozen=True):
    submission_attempt_id: str
    evidence_summary: str
    timestamp: float


class ExecutionQuarantineEntered(BaseModel, frozen=True):
    projection: QuarantineProjection
    timestamp: float


class ExecutionQuarantineResolved(BaseModel, frozen=True):
    logical_order_id: str
    resolution: str
    timestamp: float


class EmergencyCloseIntentCreated(BaseModel, frozen=True):
    intent: EmergencyCloseIntent
    timestamp: float
