"""
MarketPilot Models — Instrument information.

Instrument metadata returned by the exchange describing trading pair
specifications such as tick size, lot size, and leverage limits.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from marketpilot.core.enums import AssetType


class InstrumentInfo(BaseModel, frozen=True):
    """Trading pair specification / instrument metadata."""

    symbol: str = Field(..., description="Trading pair, e.g. 'BTCUSDT'")
    asset_type: AssetType
    base_coin: str = Field(..., description="Base currency, e.g. 'BTC'")
    quote_coin: str = Field(..., description="Quote currency, e.g. 'USDT'")
    status: str = Field(..., description="Instrument status, e.g. 'Trading'")
    tick_size: str = Field(..., description="Minimum price increment")
    min_order_qty: str = Field(..., description="Minimum order quantity")
    max_order_qty: str = Field("", description="Maximum order quantity")
    qty_step: str = Field(..., description="Quantity step size")
    min_leverage: str = Field("1", description="Minimum leverage")
    max_leverage: str = Field("1", description="Maximum leverage")
