"""
MarketPilot Models - Telegram Notification domain models.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union, Literal
from pydantic import BaseModel, Field

class NotificationSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"
    SUMMARY = "SUMMARY"

class TradeMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    NON_TRADING = "NON_TRADING"

class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    RETRYING = "RETRYING"
    FAILED = "FAILED"

class ChannelType(str, Enum):
    TELEGRAM = "TELEGRAM"

class BaseNotificationPayload(BaseModel):
    model_config = {"frozen": True}
    payload_type: str

class RuntimeSafetyPayload(BaseNotificationPayload):
    payload_type: Literal["runtime_safety"] = "runtime_safety"
    component: str
    error_code: str
    message: str

class AgentProposalPayload(BaseNotificationPayload):
    payload_type: Literal["agent_proposal"] = "agent_proposal"
    proposal_id: str
    disposition: str
    thesis_summary: str

class CandidateOutcomePayload(BaseNotificationPayload):
    payload_type: Literal["candidate_outcome"] = "candidate_outcome"
    decision_id: str
    status: str
    reason: str

class TradeLifecyclePayload(BaseNotificationPayload):
    payload_type: Literal["trade_lifecycle"] = "trade_lifecycle"
    trade_id: str
    mutation_id: str
    action: str
    fill_qty: str

class RecoveryAlertPayload(BaseNotificationPayload):
    payload_type: Literal["recovery_alert"] = "recovery_alert"
    reconciliation_record_id: str
    issue: str

class ResearchNotificationPayload(BaseNotificationPayload):
    payload_type: Literal["research_notification"] = "research_notification"
    research_run_id: str
    result: str

NotificationPayload = Union[
    RuntimeSafetyPayload,
    AgentProposalPayload,
    CandidateOutcomePayload,
    TradeLifecyclePayload,
    RecoveryAlertPayload,
    ResearchNotificationPayload
]

class NotificationEvent(BaseModel):
    model_config = {"frozen": True}
    notification_id: str
    event_type: str
    severity: NotificationSeverity
    timestamp: float
    mode: TradeMode
    source_event_id: str
    
    cycle_id: Optional[str] = None
    decision_id: Optional[str] = None
    allocation_id: Optional[str] = None
    trade_id: Optional[str] = None
    mutation_id: Optional[str] = None
    symbol: Optional[str] = None
    
    structured_payload: NotificationPayload = Field(..., discriminator="payload_type")
    schema_version: str

class NotificationDelivery(BaseModel):
    model_config = {"frozen": True}
    notification_id: str
    channel: ChannelType
    status: DeliveryStatus
    attempt_count: int
    last_attempt_at: float
    delivered_at: Optional[float] = None
    sanitized_error: Optional[str] = None
