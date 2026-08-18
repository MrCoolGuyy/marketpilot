"""
MarketPilot Engines ï¿½ Strategy Engine.

Evaluates signals using a library of strategies and ranks them
based on Confidence, Market Quality, Regime Match, and Expected RR.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from marketpilot.config.settings import StrategySettings
from marketpilot.models.causal import ClosedInstrumentSnapshot, SignalIntent, SignalDirection, StrategyIdentity
from marketpilot.models.indicators import IndicatorSeries
from marketpilot.models.regime import MarketRegime
from marketpilot.models.core import EngineMetadata
import uuid

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def evaluate(
        self,
        series: IndicatorSeries,
        regime: MarketRegime,
        snapshot: ClosedInstrumentSnapshot,
        settings: StrategySettings
    ) -> SignalIntent | None:
        """Evaluate the market data and explicitly return a SignalIntent or None if HOLD/invalid."""
        pass


class EmaPullbackStrategy(BaseStrategy):
    """Buys in an uptrend when price pulls back to the fast EMA."""

    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: ClosedInstrumentSnapshot, settings: StrategySettings) -> SignalIntent | None:
        point = series.latest
        if not point or point.ema_fast is None or point.ema_slow is None or point.atr is None or point.rsi is None:
            return None

        signal = SignalDirection.HOLD

        last_price = snapshot.facts.close

        # Long Logic
        if regime in (MarketRegime.WEAK_BULL, MarketRegime.TRENDING_BULL) and point.ema_fast > point.ema_slow:
            dist_to_ema = (last_price - point.ema_fast).copy_abs()
            if dist_to_ema < point.atr:
                signal = SignalDirection.LONG

        # Short Logic
        elif regime in (MarketRegime.WEAK_BEAR, MarketRegime.TRENDING_BEAR) and point.ema_fast < point.ema_slow:
            dist_to_ema = (last_price - point.ema_fast).copy_abs()
            if dist_to_ema < point.atr:
                signal = SignalDirection.SHORT

        if signal == SignalDirection.HOLD:
            return None

        # Risk parameters based ONLY on closed facts (no entry price assumed for execution)
        # Using the last closed price as the reference point for logical bands.
        sl_dist = point.atr * Decimal("1.5")

        if signal == SignalDirection.LONG:
            sl = last_price - sl_dist
            tp = last_price + (sl_dist * Decimal("3.0"))
        else:
            sl = last_price + sl_dist
            tp = last_price - (sl_dist * Decimal("3.0"))

        identity = StrategyIdentity(
            registry_version="1.0",
            strategy_id="ema_pullback",
            strategy_version="1.0",
            parameter_set_id="default"
        )

        return SignalIntent(
            intent_id=str(uuid.uuid4()),
            identity=identity,
            direction=signal,
            symbol=snapshot.symbol,
            signal_timestamp=snapshot.creation_timestamp,
            signal_timestamp_us=int(Decimal(str(snapshot.creation_timestamp)) * 1_000_000),
            logical_stop_loss=sl,
            logical_take_profit=tp,
            provenance_snapshot_id=snapshot.snapshot_id
        )


class MomentumStrategy(BaseStrategy):
    """Trades high momentum breakouts."""
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: ClosedInstrumentSnapshot, settings: StrategySettings) -> SignalIntent | None:
        point = series.latest
        if not point or point.rsi is None or point.atr is None:
            return None

        signal = SignalDirection.HOLD

        if point.rsi > Decimal("65") and snapshot.facts.momentum_24h > Decimal("0.05"):
            signal = SignalDirection.LONG
        elif point.rsi < Decimal("35") and snapshot.facts.momentum_24h < Decimal("-0.05"):
            signal = SignalDirection.SHORT

        if signal == SignalDirection.HOLD:
            return None

        last_price = snapshot.facts.close
        sl_dist = point.atr * Decimal("2")
        if signal == SignalDirection.LONG:
            sl = last_price - sl_dist
            tp = last_price + (sl_dist * Decimal("2.1"))
        else:
            sl = last_price + sl_dist
            tp = last_price - (sl_dist * Decimal("2.1"))

        identity = StrategyIdentity(
            registry_version="1.0",
            strategy_id="momentum",
            strategy_version="1.0",
            parameter_set_id="default"
        )

        return SignalIntent(
            intent_id=str(uuid.uuid4()),
            identity=identity,
            direction=signal,
            symbol=snapshot.symbol,
            signal_timestamp=snapshot.creation_timestamp,
            signal_timestamp_us=int(Decimal(str(snapshot.creation_timestamp)) * 1_000_000),
            logical_stop_loss=sl,
            logical_take_profit=tp,
            provenance_snapshot_id=snapshot.snapshot_id
        )


class BreakoutStrategy(BaseStrategy):
    """Simple placeholder for breakout strategy."""
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: ClosedInstrumentSnapshot, settings: StrategySettings) -> SignalIntent | None:
        return None


class TrendFollowingStrategy(BaseStrategy):
    """Simple placeholder for trend following strategy."""
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: ClosedInstrumentSnapshot, settings: StrategySettings) -> SignalIntent | None:
        return None


class StrategyEngine:
    """Evaluates multiple strategies and selects the best one based on an Overall Score."""

    def __init__(self, settings: StrategySettings):
        self._settings = settings
        self._strategies: list[BaseStrategy] = [
            EmaPullbackStrategy(),
            MomentumStrategy(),
            BreakoutStrategy(),
            TrendFollowingStrategy()
        ]

    def evaluate(
        self,
        series: IndicatorSeries,
        regime: MarketRegime,
        snapshot: ClosedInstrumentSnapshot,
        decision_id: str
    ) -> tuple[list[SignalIntent], EngineMetadata]:
        """Evaluates all strategies and returns all actionable intents + metadata."""
        start_time = time.time()

        all_intents: list[SignalIntent] = []

        for strategy in self._strategies:
            intent = strategy.evaluate(series, regime, snapshot, self._settings)
            if intent:
                all_intents.append(intent)

        processing_time_ms = (time.time() - start_time) * 1000
        metadata = EngineMetadata(processing_time_ms=processing_time_ms, decision_id=decision_id)

        return all_intents, metadata

