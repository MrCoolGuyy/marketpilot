"""
MarketPilot Strategy - Registry Service.

Canonical READ side / versioned registry foundation.
"""

from typing import Union

from marketpilot.models.registry import RegistrySnapshot, StrategyRegistryEntry, PromotionStatus
from marketpilot.models.causal import StrategyIdentity

class StrategyRegistryService:
    """Provides exact identity resolution for strategies against a specific registry version."""
    
    def __init__(self, snapshot: RegistrySnapshot):
        self._snapshot = snapshot
        
    def resolve_exact(self, identity: StrategyIdentity) -> Union[StrategyRegistryEntry, str]:
        """
        Resolves exact strategy binding against the registry.
        
        Args:
            identity: The exact causal identity to resolve.
            
        Returns:
            The StrategyRegistryEntry if exactly matched and LIVE_ELIGIBLE.
            A string rejection reason if mismatched, missing, or not live-eligible.
        """
        if identity.registry_version != self._snapshot.registry_version:
            return f"Registry version mismatch. Requested: {identity.registry_version}, Current: {self._snapshot.registry_version}"
            
        for entry in self._snapshot.entries:
            if (entry.strategy_id == identity.strategy_id and
                entry.strategy_version == identity.strategy_version and
                entry.parameter_set_id == identity.parameter_set_id):
                
                if entry.promotion_status != PromotionStatus.LIVE_ELIGIBLE:
                    return f"Strategy is not LIVE_ELIGIBLE. Status: {entry.promotion_status.value}"
                    
                return entry
                
        return f"Strategy identity not found in registry {self._snapshot.registry_version}"

    @property
    def current_version(self) -> str:
        return self._snapshot.registry_version
