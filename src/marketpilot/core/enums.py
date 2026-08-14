"""
MarketPilot Core — Enumeration types.

Centralised enum definitions for order management, asset classification,
and kline intervals.  Values match Bybit API string constants so they can
be used directly in request payloads.
"""

from __future__ import annotations

from enum import StrEnum


class AssetType(StrEnum):
    """Bybit product categories."""

    SPOT = "spot"
    LINEAR = "linear"
    INVERSE = "inverse"
    OPTION = "option"


class OrderSide(StrEnum):
    """Trade direction."""

    BUY = "Buy"
    SELL = "Sell"


class OrderType(StrEnum):
    """Order execution types."""

    LIMIT = "Limit"
    MARKET = "Market"


class TimeInForce(StrEnum):
    """Order time-in-force policies."""

    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate Or Cancel
    FOK = "FOK"  # Fill Or Kill
    POST_ONLY = "PostOnly"


class OrderStatus(StrEnum):
    """Order lifecycle states (Bybit V5)."""

    NEW = "New"
    PARTIALLY_FILLED = "PartiallyFilled"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"
    DEACTIVATED = "Deactivated"
    UNTRIGGERED = "Untriggered"
    TRIGGERED = "Triggered"


class PositionSide(StrEnum):
    """Position direction for derivatives."""

    LONG = "Buy"
    SHORT = "Sell"
    NONE = "None"  # Spot — no position concept


class Interval(StrEnum):
    """Kline / candlestick intervals.

    Values match the Bybit V5 ``interval`` parameter.
    """

    M1 = "1"
    M3 = "3"
    M5 = "5"
    M15 = "15"
    M30 = "30"
    H1 = "60"
    H2 = "120"
    H4 = "240"
    H6 = "360"
    H12 = "720"
    D1 = "D"
    W1 = "W"
    MN1 = "M"


class MarketDataEnvironment(StrEnum):
    """Source of market data."""
    
    MAINNET = "MAINNET"
    TESTNET = "TESTNET"


class ExecutionMode(StrEnum):
    """Level of execution authority."""
    
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"

