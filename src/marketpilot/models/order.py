"""
MarketPilot Models — Order domain models.

Models for order lifecycle: requests, responses, and open positions.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from marketpilot.core.enums import (
    AssetType,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
)


class OrderRequest(BaseModel, frozen=True):
    """Parameters for placing a new order."""

    symbol: str = Field(..., description="Trading pair, e.g. 'BTCUSDT'")
    asset_type: AssetType
    side: OrderSide
    order_type: OrderType
    qty: str = Field(..., description="Order quantity")
    price: str | None = Field(None, description="Limit price (required for Limit orders)")
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    close_on_trigger: bool = False


class OrderResponse(BaseModel, frozen=True):
    """Exchange response after placing / cancelling an order."""

    order_id: str
    order_link_id: str = ""
    symbol: str
    asset_type: AssetType
    side: OrderSide
    order_type: OrderType
    qty: str
    price: str = ""
    status: OrderStatus
    created_at: datetime
    updated_at: datetime


class Position(BaseModel, frozen=True):
    """An open position on the exchange."""

    symbol: str
    asset_type: AssetType
    side: PositionSide
    size: str = Field(..., description="Position size")
    entry_price: str
    mark_price: str
    unrealised_pnl: str
    leverage: str
    liq_price: str = Field("", description="Liquidation price")
    updated_at: datetime
