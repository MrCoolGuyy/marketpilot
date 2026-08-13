"""
MarketPilot Models — Indicators.

Defines deterministic data structures for technical indicators.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from marketpilot.core.enums import Interval


class IndicatorPoint(BaseModel):
    """Immutable model representing technical indicators at a specific point in time.
    
    Values are `Decimal` if sufficient data has been processed to warm them up,
    otherwise `None`.
    """
    model_config = ConfigDict(frozen=True)

    open_time: datetime = Field(description="Start time of the candle")
    
    ema_fast: Decimal | None = Field(default=None, description="Fast Exponential Moving Average")
    ema_slow: Decimal | None = Field(default=None, description="Slow Exponential Moving Average")
    
    rsi: Decimal | None = Field(default=None, description="Relative Strength Index")
    
    macd_line: Decimal | None = Field(default=None, description="MACD Line (Fast EMA - Slow EMA)")
    macd_signal: Decimal | None = Field(default=None, description="MACD Signal Line")
    macd_histogram: Decimal | None = Field(default=None, description="MACD Histogram (Line - Signal)")
    
    atr: Decimal | None = Field(default=None, description="Average True Range")
    
    volume_sma: Decimal | None = Field(default=None, description="Volume Simple Moving Average")
    
    session_vwap: Decimal | None = Field(default=None, description="Session VWAP (OHLC Approximation)")


class IndicatorSeries(BaseModel):
    """Immutable model representing a series of indicator points for an instrument."""
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="Trading pair symbol (e.g., BTCUSDT)")
    interval: Interval = Field(description="Candlestick interval")
    points: tuple[IndicatorPoint, ...] = Field(description="Chronological list of indicator points")

    @property
    def latest(self) -> IndicatorPoint | None:
        """Return the most recent IndicatorPoint, or None if empty."""
        if not self.points:
            return None
        return self.points[-1]
