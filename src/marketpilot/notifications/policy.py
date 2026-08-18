"""
MarketPilot Notifications - Presentation Policy.

Acts as the boundary between the canonical domain/read models and the outbound
presentation transport. Applies formatters and constructs raw payloads.
"""

from marketpilot.models.causal import FinalCandidate, CandidateRejectedObserved
from marketpilot.models.portfolio import (
    PortfolioAdmissionDecision,
    PortfolioExposureSnapshot,
    EquitySnapshot,
    PortfolioAllocationToken
)
from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
from marketpilot.notifications.telegram_formatters import (
    format_phase4_cycle,
    format_phase5_admission,
    format_portfolio_rejection,
    format_evidence_rejection,
    format_reservation_committed,
    format_system_status,
    format_safety_alert
)

class NotificationPolicy:
    """Translates domain execution states into rich outbound operator notifications."""

    def __init__(self, notifier):
        self.notifier = notifier

    async def notify_phase5_admission(
        self,
        candidate: FinalCandidate,
        decision: PortfolioAdmissionDecision,
        exposure: PortfolioExposureSnapshot,
        equity: EquitySnapshot
    ) -> None:
        """Emits a rich Portfolio Admission notification."""
        rendered = format_phase5_admission(candidate, decision, exposure, equity)
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.EXECUTION_SUCCESS,
            message_data={"message": rendered}
        ))

    async def notify_portfolio_rejection(
        self,
        candidate: FinalCandidate,
        decision: PortfolioAdmissionDecision,
        exposure: PortfolioExposureSnapshot
    ) -> None:
        """Emits a rich Portfolio Rejection notification."""
        rendered = format_portfolio_rejection(candidate, decision, exposure)
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.PAPER_TRADE,  # Use a neutral/info channel
            message_data={"message": rendered}
        ))

    async def notify_evidence_rejection(
        self,
        obs: CandidateRejectedObserved
    ) -> None:
        """Emits a rich Evidence Rejection notification."""
        rendered = format_evidence_rejection(
            symbol=obs.symbol,
            side=obs.direction.value,
            strategy=f"{obs.identity.strategy_id} v{obs.identity.strategy_version}",
            entry=obs.executable_entry_price,  # Might be priced
            evidence_status=obs.evidence_status.value,
            reason=obs.rejection_reason
        )
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.PAPER_TRADE,
            message_data={"message": rendered}
        ))

    async def notify_reservation_committed(
        self,
        token: PortfolioAllocationToken
    ) -> None:
        """Emits a rich Allocation Committed notification."""
        rendered = format_reservation_committed(token)
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.EXECUTION_SUCCESS,
            message_data={"message": rendered}
        ))

    async def notify_cycle_summary(
        self,
        cycle_id: str,
        time_str: str,
        mode: str,
        env: str,
        outcome: str,
        universe_size: int,
        market_qualified: int,
        signals: int,
        priced: int,
        evidence_evaluated: int,
        eligible: int,
        admitted: int,
        rejected: int,
        rejections_evidence: int,
        rejections_economics: int,
        rejections_heat: int,
        rejections_lineage: int,
        current_heat: str = "N/A",
        heat_limit: str = "N/A",
        effective_capital: str = "N/A",
        active_lineages: int = 0,
        reservations: int = 0,
        top_candidate: FinalCandidate | None = None,
        top_decision: PortfolioAdmissionDecision | None = None
    ) -> None:
        rendered = format_phase4_cycle(
            cycle_id=cycle_id,
            time_str=time_str,
            mode=mode,
            env=env,
            outcome=outcome,
            universe_size=universe_size,
            market_qualified=market_qualified,
            signals=signals,
            priced=priced,
            evidence_evaluated=evidence_evaluated,
            eligible=eligible,
            admitted=admitted,
            rejected=rejected,
            rejections_evidence=rejections_evidence,
            rejections_economics=rejections_economics,
            rejections_heat=rejections_heat,
            rejections_lineage=rejections_lineage,
            current_heat=current_heat,
            heat_limit=heat_limit,
            effective_capital=effective_capital,
            active_lineages=active_lineages,
            reservations=reservations,
            top_candidate=top_candidate,
            top_decision=top_decision
        )
        await self.notifier.notify(NotificationEvent(
            event_type=NotificationType.DAILY_SUMMARY,
            message_data={"message": rendered}
        ))
