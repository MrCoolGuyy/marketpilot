"""
MarketPilot Models — Market data domain models.

Immutable Pydantic models representing market data structures returned
by the exchange.  All monetary values use ``str`` to preserve decimal
precision; convert to ``Decimal`` in business logic.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from marketpilot.core.enums import AssetType, Interval


class Ticker(BaseModel, frozen=True):
    """Real-time ticker snapshot for a single symbol."""

    symbol: str = Field(..., description="Trading pair, e.g. 'BTCUSDT'")
    asset_type: AssetType
    last_price: str = Field(..., description="Last traded price")
    bid_price: str = Field(..., description="Best bid price")
    ask_price: str = Field(..., description="Best ask price")
    high_24h: str = Field(..., description="24-hour high")
    low_24h: str = Field(..., description="24-hour low")
    price_change_percent_24h: str = Field(..., description="24-hour price change percentage")
    volume_24h: str = Field(..., description="24-hour trading volume (base)")
    turnover_24h: str = Field(..., description="24-hour turnover (quote)")
    timestamp: datetime


class Kline(BaseModel, frozen=True):
    """Single candlestick / kline bar."""

    symbol: str
    interval: Interval
    open_time: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str
    turnover: str
    is_closed: bool = True


class OrderBookEntry(BaseModel, frozen=True):
    """A single price level in the order book."""

    price: str
    quantity: str


class OrderBook(BaseModel, frozen=True):
    """Order book snapshot."""

    symbol: str
    asset_type: AssetType
    bids: list[OrderBookEntry] = Field(default_factory=list)
    asks: list[OrderBookEntry] = Field(default_factory=list)
    timestamp: datetime


class Trade(BaseModel, frozen=True):
    """A single public trade (tick)."""

    symbol: str
    trade_id: str
    price: str
    quantity: str
    side: str
    timestamp: datetime
