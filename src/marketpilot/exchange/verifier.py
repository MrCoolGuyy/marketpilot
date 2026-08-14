"""
MarketPilot Exchange — Position Mode Verification.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from marketpilot.exchange.bybit_client import BybitClient


class VerificationStatus(StrEnum):
    """Position Mode verification status for a symbol."""
    VERIFIED_ONE_WAY = "VERIFIED_ONE_WAY"
    INCOMPATIBLE_HEDGE = "INCOMPATIBLE_HEDGE"
    UNVERIFIED = "UNVERIFIED"


class PositionModeVerifier:
    """
    Non-mutating verifier that explicitly queries Bybit to establish 
    One-Way vs Hedge mode for a specific symbol.
    """

    def __init__(self, client: BybitClient) -> None:
        self._client = client
        self._cache: dict[str, VerificationStatus] = {}

    async def verify_symbol(self, symbol: str) -> VerificationStatus:
        """
        Verify the effective position mode for a symbol.
        Returns the cached status if already verified or incompatible.
        """
        if symbol in self._cache:
            return self._cache[symbol]

        try:
            # Query the symbol explicitly
            res = await self._client.get_positions(symbol=symbol)
            result = res.get("result", {})
            list_data = result.get("list", [])
            
            if not list_data:
                # Bybit returns at least 1 object even with 0 size if the symbol is valid.
                # If empty, we cannot authoritatively verify.
                status = VerificationStatus.UNVERIFIED
            else:
                has_hedge = False
                all_one_way = True
                
                for pos in list_data:
                    idx = pos.get("positionIdx", -1)
                    if idx in (1, 2):
                        has_hedge = True
                        all_one_way = False
                    elif idx != 0:
                        all_one_way = False
                
                if has_hedge:
                    status = VerificationStatus.INCOMPATIBLE_HEDGE
                elif all_one_way and len(list_data) == 1:
                    status = VerificationStatus.VERIFIED_ONE_WAY
                else:
                    status = VerificationStatus.UNVERIFIED
                    
            self._cache[symbol] = status
            return status

        except Exception as e:
            logger.error("Failed to verify position mode for {}: {}", symbol, e)
            return VerificationStatus.UNVERIFIED

    def get_verified_symbols(self) -> list[str]:
        """Return all symbols that are VERIFIED_ONE_WAY."""
        return [sym for sym, stat in self._cache.items() if stat == VerificationStatus.VERIFIED_ONE_WAY]
        
    def get_incompatible_symbols(self) -> list[str]:
        """Return all symbols that are INCOMPATIBLE_HEDGE."""
        return [sym for sym, stat in self._cache.items() if stat == VerificationStatus.INCOMPATIBLE_HEDGE]

    def get_unverified_symbols(self) -> list[str]:
        """Return all symbols that are UNVERIFIED."""
        return [sym for sym, stat in self._cache.items() if stat == VerificationStatus.UNVERIFIED]
