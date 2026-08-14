"""
MarketPilot Engines - Exposure Manager.

Provides deterministic projection of portfolio exposure and atomic reservation semantics.
Shadow-only implementation for Phase 2.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Dict, Optional, Tuple
from threading import Lock

from pydantic import BaseModel
from marketpilot.models.portfolio import PortfolioExposureSnapshot

class ActiveExposureState(BaseModel):
    """Internal mutable state representing current exposure."""
    exposure_version: str
    timestamp: float
    active_position_ids: set[str]
    reserved_allocation_ids: set[str]
    total_heat: Decimal

class ExposureManager:
    """
    Canonical future state projection primitive.
    Handles atomic reservations and versioned CAS replacement.
    """
    
    def __init__(self):
        self._lock = Lock()
        self._state = ActiveExposureState(
            exposure_version=uuid.uuid4().hex,
            timestamp=0.0,
            active_position_ids=set(),
            reserved_allocation_ids=set(),
            total_heat=Decimal("0")
        )
        
    def _generate_version(self) -> str:
        return uuid.uuid4().hex

    def snapshot(self) -> PortfolioExposureSnapshot:
        """Returns an immutable snapshot of current exposure."""
        with self._lock:
            return PortfolioExposureSnapshot(
                exposure_version=self._state.exposure_version,
                timestamp=self._state.timestamp,
                active_position_ids=tuple(sorted(self._state.active_position_ids)),
                reserved_allocation_ids=tuple(sorted(self._state.reserved_allocation_ids)),
                total_heat=self._state.total_heat
            )

    def reserve_if_version_matches(self, allocation_id: str, required_version: str, risk: Decimal) -> bool:
        """
        Atomically reserves an allocation if the current exposure version matches the required version.
        Rejects zero or unknown risk.
        """
        if risk <= Decimal("0"):
            return False
            
        with self._lock:
            if self._state.exposure_version != required_version:
                return False
                
            if allocation_id in self._state.reserved_allocation_ids:
                return False
                
            self._state.reserved_allocation_ids.add(allocation_id)
            self._state.total_heat += risk
            self._state.exposure_version = self._generate_version()
            return True

    def replace_all(self, active_position_ids: list[str], total_heat: Decimal) -> None:
        """Hydrates or resets the exposure state from an authoritative source (e.g. recovery)."""
        with self._lock:
            self._state.active_position_ids = set(active_position_ids)
            self._state.reserved_allocation_ids.clear()
            self._state.total_heat = total_heat
            self._state.exposure_version = self._generate_version()

    def apply_confirmed_transition(self, allocation_id: str, position_id: str, new_heat: Decimal) -> None:
        """
        Transitions a reservation into an active position upon durable acknowledgement.
        """
        with self._lock:
            if allocation_id in self._state.reserved_allocation_ids:
                self._state.reserved_allocation_ids.remove(allocation_id)
                
            self._state.active_position_ids.add(position_id)
            self._state.total_heat = new_heat
            self._state.exposure_version = self._generate_version()

    def release_prepared_reservation(self, allocation_id: str, released_risk: Decimal) -> None:
        """
        Releases a prepared reservation (e.g. if submission aborts before durability).
        """
        with self._lock:
            if allocation_id in self._state.reserved_allocation_ids:
                self._state.reserved_allocation_ids.remove(allocation_id)
                self._state.total_heat = max(Decimal("0"), self._state.total_heat - released_risk)
                self._state.exposure_version = self._generate_version()
