"""
MarketPilot Scanner - Snapshot Builder.

Domain Mapping Layer that converts RawMarketData (infrastructure) 
into InstrumentSnapshot (domain), performing necessary feature engineering.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Sequence

from loguru import logger

from marketpilot.engines.indicator_engine import IndicatorEngine
from marketpilot.models.market_data import RawMarketData
from marketpilot.models.scanner import InstrumentSnapshot, TrendAge


class InstrumentSnapshotBuilder:
    """Builds InstrumentSnapshot from RawMarketData and Indicators.
    
    Deterministic domain service. Performs no API calls.
    """

    def __init__(self, indicator_engine: IndicatorEngine) -> None:
        self._indicator = indicator_engine

    def build(self, raw: RawMarketData) -> InstrumentSnapshot:
        """Construct a snapshot for a single instrument."""
        
        # Safe decimal parsing
        try:
            last_price = Decimal(raw.ticker.last_price)
            turnover_24h = Decimal(raw.ticker.turnover_24h)
            volume_24h = Decimal(raw.ticker.volume_24h)
            momentum = Decimal(raw.ticker.price_change_percent_24h)
            best_bid = Decimal(raw.ticker.bid_price)
            best_ask = Decimal(raw.ticker.ask_price)
        except InvalidOperation:
            # Fallback to zeros if ticker data is malformed
            last_price = Decimal("0")
            turnover_24h = Decimal("0")
            volume_24h = Decimal("0")
            momentum = Decimal("0")
            best_bid = Decimal("0")
            best_ask = Decimal("0")

        # 1. Calculate Spread
        spread_bps = Decimal("0")
        if best_bid > 0 and best_ask > 0 and best_ask >= best_bid:
            mid_price = (best_bid + best_ask) / Decimal("2")
            spread_bps = ((best_ask - best_bid) / mid_price) * Decimal("10000")

        # 2. Calculate Technicals
        atr_percent = Decimal("0")
        trend_strength = Decimal("0")
        trend_age_candles = 0

        if raw.klines:
            try:
                series = self._indicator.calculate(raw.klines)
                if series.points:
                    latest = series.points[-1]
                    
                    if latest.atr is not None and last_price > 0:
                        atr_percent = latest.atr / last_price
                        
                    if latest.ema_fast is not None and latest.ema_slow is not None:
                        # Simple Trend Strength: diff between fast and slow EMA / last_price
                        diff = abs(latest.ema_fast - latest.ema_slow)
                        if last_price > 0:
                            # scale it slightly to fit 0.0 - 1.0 roughly, or just use diff/price
                            ts = (diff / last_price) * Decimal("10")
                            trend_strength = min(ts, Decimal("1.0"))
                            
                        # Trend Age: look back at how long fast > slow (or vice versa)
                        is_bullish = latest.ema_fast > latest.ema_slow
                        for i in range(len(series.points) - 1, -1, -1):
                            p = series.points[i]
                            if p.ema_fast is not None and p.ema_slow is not None:
                                current_bullish = p.ema_fast > p.ema_slow
                                if current_bullish == is_bullish:
                                    trend_age_candles += 1
                                else:
                                    break
            except ValueError as exc:
                logger.debug(f"Failed to calculate indicators for {raw.symbol}: {exc}")

        return InstrumentSnapshot(
            symbol=raw.symbol,
            asset_type=raw.asset_type,
            last_price=last_price,
            liquidity_turnover_24h=turnover_24h,
            volume_24h=volume_24h,
            spread_bps=spread_bps,
            atr_percent=atr_percent,
            momentum_24h=momentum,
            trend_strength=trend_strength,
            trend_age_candles=trend_age_candles,
            funding_rate=raw.funding_rate,
            open_interest=raw.open_interest
        )
