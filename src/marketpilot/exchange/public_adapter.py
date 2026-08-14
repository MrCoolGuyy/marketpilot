"""
MarketPilot Exchange - Public Read-Only Adapter.
"""

from datetime import datetime
from typing import Any

from marketpilot.core.enums import Interval, AssetType
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.market_data import Ticker


class PublicBybitMarketDataAdapter:
    """Strictly read-only adapter wrapping BybitClient for the dashboard feed.
    
    Exposes only the safe methods required by DashboardObservationFeed.
    Does NOT expose place_order, get_positions, etc.
    """

    def __init__(self, client: BybitClient):
        self._client = client

    async def connect(self) -> None:
        """Initialise the pybit HTTP session."""
        await self._client.connect()

    async def disconnect(self) -> None:
        """Release the HTTP session."""
        if hasattr(self._client, "disconnect"):
            await self._client.disconnect()
        elif hasattr(self._client, "close"):
            await self._client.close()

    async def get_server_time(self) -> datetime:
        """Fetch the exchange server time."""
        return await self._client.get_server_time()

    async def get_klines(
        self,
        symbol: str,
        interval: Interval,
        limit: int = 200,
        asset_type: AssetType = AssetType.LINEAR,
    ) -> list:
        """Fetch klines/candlestick data."""
        return await self._client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            asset_type=asset_type
        )

    async def get_tickers(
        self,
        symbol: str,
        asset_type: AssetType = AssetType.LINEAR,
    ) -> list[Ticker]:
        """Fetch ticker(s) for a symbol."""
        return await self._client.get_tickers(
            symbol=symbol,
            asset_type=asset_type
        )
