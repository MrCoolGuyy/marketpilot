"""
MarketPilot Models - Scanner domain models.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict
from enum import Enum

from pydantic import BaseModel, Field

from marketpilot.core.enums import AssetType
from marketpilot.models.core import EngineMetadata


class TrendAge(str, Enum):
    """Classification of how long a trend has been active based on 1H candles."""
    NEW = "NEW"       # 0-5 candles
    EARLY = "EARLY"     # 6-24 candles
    MATURE = "MATURE"    # 25-72 candles
    LATE = "LATE"      # >72 candles


class InstrumentSnapshot(BaseModel):
    """A raw snapshot of an instrument's market data."""
    
    symbol: str = Field(..., description="Trading pair, e.g. 'BTCUSDT'")
    asset_type: AssetType = Field(default=AssetType.LINEAR)
    
    last_price: Decimal = Field(..., description="Last traded price")
    
    # Required Metrics
    liquidity_turnover_24h: Decimal = Field(..., description="24-hour turnover (quote coin volume)")
    volume_24h: Decimal = Field(..., description="24-hour volume (base coin volume)")
    spread_bps: Decimal = Field(..., description="Bid-Ask spread in basis points (e.g. 5.0 = 0.05%)")
    atr_percent: Decimal = Field(..., description="ATR as a percentage of price (e.g. 0.05 = 5%)")
    momentum_24h: Decimal = Field(..., description="24-hour price change percentage (e.g. 0.05 = 5%)")
    trend_strength: Decimal = Field(..., description="Trend strength indicator (0.0 to 1.0)")
    trend_age_candles: int = Field(..., description="Number of candles the current trend has been active")
    
    # Optional Metrics
    funding_rate: Decimal | None = Field(default=None, description="Current funding rate")
    open_interest: Decimal | None = Field(default=None, description="Current open interest in base coin")

    # Output Metrics
    market_quality: Decimal | None = Field(default=None, description="Market Quality Score (0-100)")
    trend_age: TrendAge | None = Field(default=None, description="Categorized Trend Age")
    score_breakdown: Dict[str, str] = Field(default_factory=dict, description="Penalty-based score breakdown")


class ScannerResult(BaseModel):
    """The final ranked result from the ScannerEngine."""
    
    top_candidates: list[InstrumentSnapshot] = Field(..., description="Ranked list of instruments, highest score first")
    market_health: Decimal = Field(..., description="Overall aggregated health of the market (0-100)")
    timestamp: float = Field(..., description="Unix timestamp of the scan")
    metadata: EngineMetadata = Field(default_factory=EngineMetadata)

