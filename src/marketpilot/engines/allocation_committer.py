"""
MarketPilot Engines - Allocation Committer.

Durably commits Phase-5 capital reservations using the canonical journal protocol.
"""

import time
from marketpilot.models.portfolio import PortfolioAllocationToken
from marketpilot.models.journal import ReservationPrepared, AllocationCommitted, ReservationAborted
from marketpilot.engines.journal_engine import JournalEngine

class AllocationCommitter:
    """
    Durable capital-admission commit boundary for Phase 5.
    """

    def __init__(self, journal_engine: JournalEngine = None):
        self.journal_engine = journal_engine or JournalEngine()

    def prepare_reservation(self, token: PortfolioAllocationToken) -> None:
        """
        Durably write the intent to disk as a PREPARE event.
        """
        event = ReservationPrepared(
            allocation_id=token.reservation_identity,
            lineage_identity=token.lineage_identity,
            risk_amount=token.candidate_risk_amount,
            timestamp=time.time()
        )
        self.journal_engine.append_durable_event(event)

    def commit_allocation(self, token: PortfolioAllocationToken) -> PortfolioAllocationToken:
        """
        Durably commits the approved capital reservation.
        This does not create execution authority or an active exchange position.
        """
        event = AllocationCommitted(
            allocation_id=token.reservation_identity,
            lineage_identity=token.lineage_identity,
            risk_amount=token.candidate_risk_amount,
            timestamp=time.time()
        )
        self.journal_engine.append_durable_event(event)
        return token

    def abort_reservation(self, allocation_id: str, reason: str) -> None:
        """
        Durably record a failed or aborted reservation.
        """
        event = ReservationAborted(
            allocation_id=allocation_id,
            reason=reason,
            timestamp=time.time()
        )
        self.journal_engine.append_durable_event(event)
