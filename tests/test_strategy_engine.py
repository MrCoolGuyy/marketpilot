"""Tests for Strategy Engine."""

from datetime import datetime, UTC
from decimal import Decimal
import pytest

from marketpilot.config.settings import StrategySettings
from marketpilot.engines.strategy_engine import StrategyEngine
from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
from marketpilot.models.regime import MarketRegime
from marketpilot.models.causal import ClosedInstrumentSnapshot, MarketFacts, SignalDirection
from marketpilot.core.enums import AssetType, Interval, MarketDataEnvironment
import time

def test_strategy_engine_ema_pullback() -> None:
    settings = StrategySettings(minimum_rr=2.0)
    engine = StrategyEngine(settings)
    
    point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("90"),
        rsi=Decimal("45"),
        atr=Decimal("2")
    )
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(point,))
    
    now = time.time()
    facts = MarketFacts(
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("20"),
        turnover=Decimal("1000000"),
        spread_bps=Decimal("10"),
        atr_percent=Decimal("0.02"),
        momentum_24h=Decimal("0.01"),
        trend_strength=Decimal("0.2"),
        trend_age_candles=10
    )
    
    snap = ClosedInstrumentSnapshot(
        snapshot_id="test-snap",
        symbol="BTCUSDT",
        interval=Interval.H1,
        environment=MarketDataEnvironment.MAINNET,
        candle_open_time=now - 3600,
        candle_close_time=now - 100,
        creation_timestamp=now,
        feature_set_version="1.0",
        facts=facts
    )
    
    # Eval with decision_id
    all_intents, metadata = engine.evaluate(series, MarketRegime.TRENDING_BULL, snap, decision_id="test-123")
    
    # We expect EMA Pullback to trigger LONG
    assert len(all_intents) > 0
    
    best_intent = None
    for intent in all_intents:
        if intent.identity.strategy_id == "ema_pullback":
            best_intent = intent
            break
            
    assert best_intent is not None
    assert best_intent.direction == SignalDirection.LONG
    
    # Risk calculation verification based on ATR (which is 2.0)
    # SL = close(101) - 1.5 * atr(2) = 101 - 3 = 98
    # TP = close(101) + 3.0 * atr(2) = 101 + 6 = 107
    assert best_intent.logical_stop_loss == Decimal("98.00")
    # Wait, the tp logic was: tp = close + (sl_dist * 3) = close + (3 * 3) = 110!
    # sl_dist = 1.5 * atr = 3. 3 * 3.0 = 9. 101 + 9 = 110.
    assert best_intent.logical_take_profit == Decimal("110.00")
    
    assert metadata.decision_id == "test-123"
