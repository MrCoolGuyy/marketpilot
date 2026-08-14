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
from marketpilot.models.causal import ClosedInstrumentSnapshot, MarketFacts, SnapshotBuildOutcome, SnapshotBuildResult
import uuid
from marketpilot.core.time import CandleBoundaryResolver, MarketObservationClock


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

    def build_causal(self, raw: RawMarketData, clock: MarketObservationClock) -> SnapshotBuildResult:
        """
        Construct a causal snapshot guaranteed to only contain closed candles.
        Any forming candle is explicitly stripped.
        """
        if not raw.klines:
            return SnapshotBuildResult(outcome=SnapshotBuildOutcome.NO_CLOSED_CANDLES, reason="Raw klines list is empty.")

        # Ensure ascending order before finalization processing
        sorted_klines = sorted(raw.klines, key=lambda k: k.open_time)
        
        # Ensure strictly monotonic (no duplicates)
        for i in range(1, len(sorted_klines)):
            if sorted_klines[i].open_time <= sorted_klines[i-1].open_time:
                logger.warning(f"Non-monotonic history detected for {raw.symbol}, rejecting snapshot.")
                return SnapshotBuildResult(outcome=SnapshotBuildOutcome.NON_MONOTONIC_HISTORY, reason="Raw history contains non-monotonic or duplicate timestamps.")

        # Exclude forming candles using the authoritative clock
        closed_klines = []
        for k in sorted_klines:
            open_sec = k.open_time.timestamp()
            
            # Use explicit confirmation if available (e.g. from WebSocket)
            if hasattr(k, 'confirm') and k.confirm is not None:
                if k.confirm:
                    closed_klines.append(k)
                continue
                
            # Otherwise use time-boundary resolution
            if CandleBoundaryResolver.is_closed(open_sec, k.interval, clock):
                closed_klines.append(k)
                
        if not closed_klines:
            return SnapshotBuildResult(outcome=SnapshotBuildOutcome.NO_CLOSED_CANDLES, reason="All available candles are still forming.")
            
        boundary_candle = closed_klines[-1]

        # Calculate Technicals on CLOSED history only
        atr_percent = Decimal("0")
        trend_strength = Decimal("0")
        trend_age_candles = 0
        
        last_close_price = Decimal(boundary_candle.close)

        try:
            series = self._indicator.calculate(closed_klines)
            if series.points:
                latest = series.points[-1]
                
                if latest.atr is not None and last_close_price > 0:
                    atr_percent = latest.atr / last_close_price
                    
                if latest.ema_fast is not None and latest.ema_slow is not None:
                    diff = abs(latest.ema_fast - latest.ema_slow)
                    if last_close_price > 0:
                        ts = (diff / last_close_price) * Decimal("10")
                        trend_strength = min(ts, Decimal("1.0"))
                        
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
            logger.debug(f"Failed to calculate indicators for causal {raw.symbol}: {exc}")

        # Basic facts
        try:
            best_bid = Decimal(raw.ticker.bid_price)
            best_ask = Decimal(raw.ticker.ask_price)
            momentum = Decimal(raw.ticker.price_change_percent_24h)
        except InvalidOperation:
            best_bid = Decimal("0")
            best_ask = Decimal("0")
            momentum = Decimal("0")
            
        spread_bps = Decimal("0")
        if best_bid > 0 and best_ask > 0 and best_ask >= best_bid:
            mid_price = (best_bid + best_ask) / Decimal("2")
            spread_bps = ((best_ask - best_bid) / mid_price) * Decimal("10000")

        facts = MarketFacts(
            open=Decimal(boundary_candle.open),
            high=Decimal(boundary_candle.high),
            low=Decimal(boundary_candle.low),
            close=last_close_price,
            volume=Decimal(boundary_candle.volume),
            turnover=Decimal(boundary_candle.turnover),
            spread_bps=spread_bps,
            atr_percent=atr_percent,
            momentum_24h=momentum,
            trend_strength=trend_strength,
            trend_age_candles=trend_age_candles,
            funding_rate=raw.funding_rate,
            open_interest=raw.open_interest,
            market_quality_score=None
        )

        from marketpilot.core.enums import MarketDataEnvironment
        # Ideally environment is passed down, but for V1 we hardcode MAINNET here
        # or determine it if possible. We will assume MAINNET if not provided elsewhere for now.
        env = MarketDataEnvironment.MAINNET

        # Derive candle close time from open_time + interval
        try:
            candle_close_time = CandleBoundaryResolver.get_close_time(boundary_candle.open_time.timestamp(), boundary_candle.interval)
        except ValueError as e:
            return SnapshotBuildResult(outcome=SnapshotBuildOutcome.INVALID_INTERVAL, reason=str(e))
        
        # Enforce that candle_close_time is strictly in the past compared to creation_timestamp
        creation_ts = clock.observed_at
        if candle_close_time > creation_ts:
            logger.warning(f"Future leakage prevented for {raw.symbol}. Closed candle time {candle_close_time} > now {creation_ts}")
            return SnapshotBuildResult(outcome=SnapshotBuildOutcome.INVALID_CAUSAL_BOUNDARY, reason="Boundary candle closes in the future relative to observation clock.")

        snapshot = ClosedInstrumentSnapshot(
            snapshot_id=str(uuid.uuid4()),
            symbol=raw.symbol,
            interval=boundary_candle.interval,
            environment=env,
            candle_open_time=boundary_candle.open_time.timestamp(),
            candle_close_time=candle_close_time,
            creation_timestamp=creation_ts,
            feature_set_version="1.0",
            facts=facts
        )
        return SnapshotBuildResult(outcome=SnapshotBuildOutcome.BUILT, snapshot=snapshot)
