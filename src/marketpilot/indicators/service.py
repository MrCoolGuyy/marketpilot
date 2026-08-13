"""
MarketPilot Indicators � Service.

Calculates technical indicators from Kline data.
This service acts as a facade over the deterministic IndicatorEngine.
"""

from __future__ import annotations

from typing import Sequence

from marketpilot.config.settings import IndicatorSettings
from marketpilot.models.indicators import IndicatorSeries
from marketpilot.models.market import Kline


class IndicatorService:
    """Calculates technical indicators from Kline data.
    
    This service acts as a facade over the deterministic IndicatorEngine.
    """

    def __init__(self, settings: IndicatorSettings) -> None:
        from marketpilot.engines.indicator_engine import IndicatorEngine
        self._engine = IndicatorEngine(settings)

    def calculate(self, klines: Sequence[Kline]) -> IndicatorSeries:
        """Calculate indicators for a series of Klines.
        
        Parameters
        ----------
        klines : Sequence[Kline]
            The historical kline data.
            
        Returns
        -------
        IndicatorSeries
            An immutable series of indicator points aligned with the input candles.
        """
        return self._engine.calculate(klines)
