"""
MarketPilot Engines — Regime Engine.

Deterministically classifies the current market regime based on indicator data.
"""

from decimal import Decimal

from marketpilot.models.indicators import IndicatorSeries, IndicatorPoint
from marketpilot.models.regime import MarketRegime

class RegimeEngine:
    """Classifies the market regime deterministically based on IndicatorSeries."""

    def __init__(self, high_volatility_threshold: Decimal = Decimal("0.05"), low_volatility_threshold: Decimal = Decimal("0.01")):
        self.high_volatility = high_volatility_threshold
        self.low_volatility = low_volatility_threshold

    def evaluate(self, series: IndicatorSeries, current_price: Decimal) -> MarketRegime:
        """Evaluate the current market regime based on the latest indicators.
        
        Rules:
        - HIGH_VOLATILITY: ATR / price > high_volatility_threshold
        - LOW_VOLATILITY: ATR / price < low_volatility_threshold
        - TRENDING_BULL: fast_ema > slow_ema AND price > fast_ema AND rsi > 55
        - TRENDING_BEAR: fast_ema < slow_ema AND price < fast_ema AND rsi < 45
        - WEAK_BULL: fast_ema > slow_ema but price <= fast_ema
        - WEAK_BEAR: fast_ema < slow_ema but price >= fast_ema
        - RANGING: Otherwise
        """
        point = series.latest
        if not point or point.ema_fast is None or point.ema_slow is None or point.rsi is None or point.atr is None:
            return MarketRegime.RANGING

        # Check Volatility first
        if current_price > Decimal("0"):
            volatility = point.atr / current_price
            if volatility > self.high_volatility:
                return MarketRegime.HIGH_VOLATILITY
            if volatility < self.low_volatility:
                return MarketRegime.LOW_VOLATILITY

        # Check Trend
        fast = point.ema_fast
        slow = point.ema_slow
        rsi = point.rsi

        if fast > slow:
            if current_price > fast and rsi > Decimal("55"):
                return MarketRegime.TRENDING_BULL
            return MarketRegime.WEAK_BULL
            
        if fast < slow:
            if current_price < fast and rsi < Decimal("45"):
                return MarketRegime.TRENDING_BEAR
            return MarketRegime.WEAK_BEAR

        return MarketRegime.RANGING
