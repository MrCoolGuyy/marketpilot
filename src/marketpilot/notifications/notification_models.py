"""
MarketPilot Notifications - Data Models.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class NotificationType(str, Enum):
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    CIRCUIT_BREAKER_HALTED = "CIRCUIT_BREAKER_HALTED"
    CIRCUIT_BREAKER_RECOVERED = "CIRCUIT_BREAKER_RECOVERED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_FINISHED = "RECOVERY_FINISHED"
    RECOVERY_FAILED = "RECOVERY_FAILED"
    EXECUTION_SUCCESS = "EXECUTION_SUCCESS"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"
    PAPER_TRADE = "PAPER_TRADE"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    CRITICAL_INCIDENT_P0 = "CRITICAL_INCIDENT_P0"
    CRITICAL_INCIDENT_P1 = "CRITICAL_INCIDENT_P1"

class NotificationEvent(BaseModel):
    """An event dispatched for notification."""
    event_type: NotificationType
    decision_id: Optional[str] = None
    message_data: dict[str, str] = Field(default_factory=dict)
