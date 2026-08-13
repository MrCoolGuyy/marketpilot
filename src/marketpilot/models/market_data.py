"""
MarketPilot Models - Market Data Ingestion Models.
"""

from __future__ import annotations

from decimal import Decimal
from pydantic import BaseModel, Field
from marketpilot.core.enums import AssetType
from marketpilot.models.market import Kline, Ticker

class RawMarketData(BaseModel):
    """Raw data snapshot directly from the exchange, pre-engineering."""
    
    symbol: str = Field(..., description="Trading pair, e.g. 'BTCUSDT'")
    asset_type: AssetType = Field(default=AssetType.LINEAR)
    
    # Raw Data from Exchange
    ticker: Ticker = Field(..., description="Latest ticker data")
    klines: list[Kline] = Field(default_factory=list, description="Recent klines")
    
    # Optional Data
    orderbook: dict | None = Field(default=None, description="Optional orderbook state")
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    
    timestamp: float = Field(..., description="Local timestamp when data was fetched")
