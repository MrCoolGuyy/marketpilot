"""
MarketPilot Models — Regime.

Defines the market regime classification enum.
"""

from enum import Enum

class MarketRegime(str, Enum):
    """Classifications of the current market state."""
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    WEAK_BULL = "WEAK_BULL"
    WEAK_BEAR = "WEAK_BEAR"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
