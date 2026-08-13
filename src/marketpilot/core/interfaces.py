"""
MarketPilot Core — Abstract interfaces.

These ABCs define the contracts that concrete implementations must fulfil.
They enforce the Dependency Inversion Principle: high-level modules depend
on abstractions, not on concrete exchange clients or storage backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from marketpilot.core.enums import AssetType, Interval, OrderSide, OrderType, TimeInForce
from marketpilot.models.market import Kline, OrderBook, Ticker
from marketpilot.models.order import OrderRequest, OrderResponse, Position
from marketpilot.models.account import Balance


# ---------------------------------------------------------------------------
# Exchange Client
# ---------------------------------------------------------------------------

class BaseExchangeClient(ABC):
    """Contract for exchange API adapters (Bybit, etc.)."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection / authenticate with the exchange."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close connections."""

    # -- Market Data --------------------------------------------------------

    @abstractmethod
    async def get_ticker(self, symbol: str, asset_type: AssetType) -> Ticker:
        """Fetch the latest ticker for *symbol*."""

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: Interval,
        asset_type: AssetType,
        *,
        limit: int = 200,
    ) -> list[Kline]:
        """Fetch historical kline / candlestick data."""

    @abstractmethod
    async def get_orderbook(
        self,
        symbol: str,
        asset_type: AssetType,
        *,
        limit: int = 25,
    ) -> OrderBook:
        """Fetch current order book snapshot."""

    # -- Trading ------------------------------------------------------------

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Submit a new order to the exchange."""

    @abstractmethod
    async def cancel_order(
        self,
        symbol: str,
        order_id: str,
        asset_type: AssetType,
    ) -> OrderResponse:
        """Cancel an existing order."""

    @abstractmethod
    async def get_positions(self, asset_type: AssetType) -> list[Position]:
        """Retrieve all open positions for the given asset type."""

    # -- Account ------------------------------------------------------------

    @abstractmethod
    async def get_balances(self) -> list[Balance]:
        """Retrieve wallet balances."""


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class BaseScanner(ABC):
    """Contract for market scanners / screeners."""

    @abstractmethod
    async def scan(self) -> list[dict[str, Any]]:
        """Run the scanning logic and return results."""

    @abstractmethod
    async def start(self) -> None:
        """Start continuous scanning."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop continuous scanning."""


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

class BaseStorage(ABC):
    """Contract for persistence backends."""

    @abstractmethod
    async def initialize(self) -> None:
        """Create tables / indices if they don't exist."""

    @abstractmethod
    async def close(self) -> None:
        """Release database connections."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` if the storage backend is reachable."""
