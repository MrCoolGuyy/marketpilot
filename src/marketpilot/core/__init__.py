"""
MarketPilot Core — Foundation abstractions and contracts.

This package defines the base exceptions, interfaces, enums, and constants
that form the backbone of the MarketPilot trading system.
"""

from marketpilot.core.enums import (
    AssetType,
    Interval,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
)
from marketpilot.core.exceptions import (
    ConfigError,
    ExchangeError,
    MarketPilotError,
    StorageError,
    ValidationError,
)

__all__: list[str] = [
    # Exceptions
    "MarketPilotError",
    "ConfigError",
    "ExchangeError",
    "StorageError",
    "ValidationError",
    # Enums
    "AssetType",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderStatus",
    "Interval",
    "PositionSide",
]
