"""MarketPilot Models — Demo Execution."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from marketpilot.core.enums import OrderSide, OrderType, OrderStatus

class DemoOrderRecord(BaseModel):
    """Immutable audit trail record for a Demo Trading order."""
    
    order_link_id: str = Field(description="Client-generated idempotent UUID")
    order_id: str = Field(default="", description="Exchange-generated order ID")
    symbol: str = Field(description="Trading pair symbol")
    side: OrderSide = Field(description="Order side")
    order_type: OrderType = Field(description="Order type")
    
    quantity: Decimal = Field(description="Requested quantity")
    price: Decimal | None = Field(default=None, description="Requested limit price if applicable")
    
    status: OrderStatus = Field(default=OrderStatus.NEW, description="Last known status")
    filled_quantity: Decimal = Field(default=Decimal("0"), description="Quantity filled")
    avg_fill_price: Decimal | None = Field(default=None, description="Average execution price")
    
    created_at: datetime = Field(description="Time of creation")
    updated_at: datetime = Field(description="Time of last status update")
    
    risk_snapshot: dict[str, Any] = Field(default_factory=dict, description="Snapshot of risk assessment")
    raw_response: dict[str, Any] = Field(default_factory=dict, description="Raw Bybit response for audit")
