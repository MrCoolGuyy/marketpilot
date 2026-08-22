from typing import List
import time
from marketpilot.models.execution import (
    ExecutionIntent,
    ExecutionQuoteSnapshot,
    NetworkPermit,
    ExecutionFill,
    PaperFillRole
)
from marketpilot.models.journal import (
    ExecutionValidationRejected,
    ExecutionAcknowledgmentObserved,
    ExecutionFillObserved,
    ExecutionProtectionObserved
)
from pydantic import BaseModel
from marketpilot.engines.paper_simulator import PaperSimulator, PaperSimulationRejected
from marketpilot.models.execution_policy import PaperExecutionPolicy
from marketpilot.strategy.portfolio_policy import PortfolioPolicy
from decimal import Decimal

class PaperAdapter:
    """Thin wrapper around PaperSimulator returning canonical events."""

    def __init__(self, simulator: PaperSimulator, paper_policy: PaperExecutionPolicy, portfolio_policy: PortfolioPolicy):
        self._simulator = simulator
        self._paper_policy = paper_policy
        self._portfolio_policy = portfolio_policy

    def evaluate_entry(self, intent: ExecutionIntent, quote: ExecutionQuoteSnapshot, permit: NetworkPermit) -> List[BaseModel]:
        events = []
        try:
            # We mock current portfolio heat and risk for this thin wrapper for now,
            # ideally these come from PortfolioAllocator or ExposureManager.
            obs = self._simulator.evaluate_entry(
                intent=intent,
                quote=quote,
                paper_policy=self._paper_policy,
                portfolio_policy=self._portfolio_policy,
                current_portfolio_heat=Decimal("0.0"),
                allocation_reserved_risk=Decimal("0.0"),
                max_allowed_risk=Decimal("200.0")
            )

            # Translate to canonical
            events.append(ExecutionAcknowledgmentObserved(
                submission_attempt_id=permit.submission_attempt_id,
                order_id=f"sim-order-{permit.submission_attempt_id}",
                timestamp=time.time()
            ))

            fill = ExecutionFill(
                exec_id=obs.fill_id,
                order_id=f"sim-order-{permit.submission_attempt_id}",
                order_link_id=intent.logical_order_id,
                symbol=intent.symbol,
                side=intent.side,
                exec_qty=obs.qty,
                exec_price=obs.fill_price,
                fee=obs.fee,
                timestamp=obs.timestamp,
                environment="PAPER"
            )
            events.append(ExecutionFillObserved(
                submission_attempt_id=permit.submission_attempt_id,
                fill=fill
            ))

            events.append(ExecutionProtectionObserved(
                submission_attempt_id=permit.submission_attempt_id,
                protection_state="CONFIRMED",
                timestamp=time.time()
            ))

        except PaperSimulationRejected as e:
            events.append(ExecutionValidationRejected(
                intent_id=intent.intent_id,
                reason=e.reason,
                timestamp=time.time()
            ))

        return events
