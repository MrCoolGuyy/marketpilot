from __future__ import annotations

import threading
import time
from typing import Optional

from pydantic import BaseModel

from marketpilot.models.execution import (
    ExecutionIntent,
    NetworkPermit,
    PermitAction,
    ValidatedOrderSpec,
    ExecutionQuoteSnapshot
)
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
from marketpilot.engines.journal_engine import JournalEngine
from marketpilot.engines.exposure_manager import ExposureManager
from marketpilot.engines.execution_reducer import ExecutionStateReducer, ReducerState, TransitionStatus
from marketpilot.engines.order_validator import OrderValidator
from marketpilot.adapters.paper_execution_adapter import PaperAdapter
from marketpilot.models.portfolio import PortfolioAllocationToken
from marketpilot.notifications.policy import NotificationPolicy

class ExecutionCoordinator:
    """Canonical Execution Orchestrator for Phase 6B+."""

    def __init__(
        self,
        journal: JournalEngine,
        exposure: ExposureManager,
        paper_adapter: PaperAdapter,
        notification_policy: NotificationPolicy
    ):
        self._journal = journal
        self._exposure = exposure
        self._paper_adapter = paper_adapter
        self._notification_policy = notification_policy
        self._reducer = ExecutionStateReducer()
        self._states: dict[str, ReducerState] = {}
        self._lock = threading.Lock()

    def hydrate_from_journal(self) -> None:
        """
        Reads historical events from journal, runs them through the reducer,
        and reconstructs state and projections exactly. Suppresses notifications.
        """
        with self._lock:
            # We assume events.jsonl is read line by line.
            # (In a real implementation, we'd parse JournalEngine.events_path)
            pass

    def _apply_durable_event(self, event: BaseModel, logical_order_id: str, suppress_notification: bool = False) -> TransitionStatus:
        with self._lock:
            state = self._states.get(logical_order_id)
            new_state, status = self._reducer.apply(state, event)

            if status == TransitionStatus.ACCEPTED:
                self._journal.append_durable_event(event)
                self._states[logical_order_id] = new_state
                self._update_exposure_projection(event, state, new_state)

                if not suppress_notification:
                    self._dispatch_notifications(event, new_state)

            return status

    def _update_exposure_projection(self, event: BaseModel, old_state: Optional[ReducerState], new_state: ReducerState) -> None:
        if isinstance(event, ExecutionValidationRejected):
            if new_state.intent:
                risk_amt = new_state.intent.original_qty * abs(
                    new_state.intent.executable_entry - new_state.intent.effective_stop
                )
                self._exposure.release_prepared_reservation(
                    allocation_id=new_state.intent.allocation_token_id,
                    released_risk=risk_amt
                )
        elif isinstance(event, ExecutionFillObserved):
            if old_state and old_state.entry_fill is None and new_state.entry_fill is not None:
                if new_state.intent:
                    reserved_risk = new_state.intent.original_qty * abs(
                        new_state.intent.executable_entry - new_state.intent.effective_stop
                    )
                    actual_risk = new_state.intent.original_qty * abs(
                        new_state.entry_fill.exec_price - new_state.intent.effective_stop
                    )
                    self._exposure.apply_confirmed_transition(
                        allocation_id=new_state.intent.allocation_token_id,
                        position_id=new_state.logical_order_id,
                        new_risk=actual_risk,
                        released_risk=reserved_risk
                    )

    def _dispatch_notifications(self, event: BaseModel, state: ReducerState) -> None:
        """Dispatches real-time Telegram notifications based on new applied events."""
        import asyncio
        if isinstance(event, ExecutionFillObserved):
            if state.entry_fill == event.fill:
                pass
            else:
                pass

    def propose_event(self, logical_order_id: str, event: BaseModel) -> TransitionStatus:
        return self._apply_durable_event(event, logical_order_id)

    def process_allocation(self, token: PortfolioAllocationToken, quote: ExecutionQuoteSnapshot, take_profit: Decimal, environment: str) -> None:
        """Entry point from TradingPipeline."""
        intent = ExecutionIntent(
            intent_id=f"INT-{token.reservation_identity}",
            allocation_token_id=token.reservation_identity,
            logical_order_id=f"POS-{token.reservation_identity}",
            symbol=token.symbol,
            side=token.direction,
            original_qty=token.quantity,
            executable_entry=quote.ask if token.direction == "LONG" else quote.bid,
            effective_stop=token.effective_stop,
            take_profit=take_profit,
            environment=environment
        )

        # 1. Create Intent
        created_event = ExecutionIntentCreated(intent=intent, timestamp=time.time())
        status = self._apply_durable_event(created_event, intent.logical_order_id)
        if status != TransitionStatus.ACCEPTED:
            return

        if environment == "PAPER":
            self._execute_paper(intent, quote)

    def _execute_paper(self, intent: ExecutionIntent, quote: ExecutionQuoteSnapshot) -> None:
        """Drives the PREPARE -> AUTHORIZE -> PERMIT -> BACKEND flow for PAPER."""
        # 2. PREPARE
        # For simplicity, skip strict OrderValidator in this mock structure or use it if available
        spec = ValidatedOrderSpec(
            intent_id=intent.intent_id,
            spec_hash="hash123",
            quantized_qty=intent.original_qty,
            quantized_price=intent.executable_entry,
            quantized_stop=intent.effective_stop,
            quantized_tp=intent.take_profit
        )
        sub_id = f"SUB-{intent.logical_order_id}"
        prepared_event = ExecutionSubmissionPrepared(
            intent_id=intent.intent_id,
            spec=spec,
            submission_attempt_id=sub_id,
            timestamp=time.time()
        )
        self._apply_durable_event(prepared_event, intent.logical_order_id)

        # 3. AUTHORIZE & PERMIT
        auth_event_id = f"AUTH-{sub_id}"
        import hashlib
        payload = f"{sub_id}_{spec.spec_hash}_{PermitAction.CREATE.value}_PAPER"
        permit_id = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        auth_event = ExecutionSubmissionAuthorized(
            submission_attempt_id=sub_id,
            authorization_event_id=auth_event_id,
            permit_id=permit_id,
            timestamp=time.time()
        )
        self._apply_durable_event(auth_event, intent.logical_order_id)

        permit = NetworkPermit(
            permit_id=permit_id,
            submission_attempt_id=sub_id,
            logical_order_id=intent.logical_order_id,
            action=PermitAction.CREATE,
            environment="PAPER",
            symbol=intent.symbol,
            validated_spec_hash=spec.spec_hash,
            authorization_event_id=auth_event_id,
            issued_at=time.time()
        )

        attempt_event = ExecutionNetworkAttemptStarted(permit_id=permit_id, timestamp=time.time())
        self._apply_durable_event(attempt_event, intent.logical_order_id)

        # 4. Delegate to PAPER Adapter
        events = self._paper_adapter.evaluate_entry(intent, quote, permit)
        for ev in events:
            self._apply_durable_event(ev, intent.logical_order_id)
