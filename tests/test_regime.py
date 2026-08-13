"""Tests for Regime Engine."""

from datetime import datetime, UTC
from decimal import Decimal

from marketpilot.core.enums import Interval
from marketpilot.engines.regime_engine import RegimeEngine
from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
from marketpilot.models.regime import MarketRegime

def test_regime_engine_volatility() -> None:
    engine = RegimeEngine(high_volatility_threshold=Decimal("0.05"), low_volatility_threshold=Decimal("0.01"))
    
    # Setup base point
    base_point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("90"),
        rsi=Decimal("60"),
        atr=Decimal("10"), # High Volatility! 10 / 100 = 0.1 > 0.05
    )
    
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(base_point,))
    
    # Should evaluate to HIGH_VOLATILITY regardless of trend
    assert engine.evaluate(series, current_price=Decimal("100")) == MarketRegime.HIGH_VOLATILITY

    # Low Volatility: ATR = 0.5 -> 0.5 / 100 = 0.005 < 0.01
    base_point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("90"),
        rsi=Decimal("60"),
        atr=Decimal("0.5"),
    )
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(base_point,))
    assert engine.evaluate(series, current_price=Decimal("100")) == MarketRegime.LOW_VOLATILITY

def test_regime_engine_trending() -> None:
    engine = RegimeEngine(high_volatility_threshold=Decimal("0.5"), low_volatility_threshold=Decimal("0.001"))
    
    # TRENDING_BULL: fast > slow, price > fast, rsi > 55
    point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("90"),
        rsi=Decimal("60"),
        atr=Decimal("2"), # 2/110 = 0.018 (Normal Volatility)
    )
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(point,))
    assert engine.evaluate(series, current_price=Decimal("110")) == MarketRegime.TRENDING_BULL

    # WEAK_BULL: fast > slow, but price <= fast
    assert engine.evaluate(series, current_price=Decimal("95")) == MarketRegime.WEAK_BULL

    # WEAK_BULL: fast > slow, price > fast, but rsi <= 55
    point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("100"),
        ema_slow=Decimal("90"),
        rsi=Decimal("50"),
        atr=Decimal("2"),
    )
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(point,))
    assert engine.evaluate(series, current_price=Decimal("110")) == MarketRegime.WEAK_BULL

    # TRENDING_BEAR: fast < slow, price < fast, rsi < 45
    point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal("90"),
        ema_slow=Decimal("100"),
        rsi=Decimal("40"),
        atr=Decimal("2"),
    )
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(point,))
    assert engine.evaluate(series, current_price=Decimal("80")) == MarketRegime.TRENDING_BEAR

    # WEAK_BEAR: fast < slow, but price >= fast
    assert engine.evaluate(series, current_price=Decimal("95")) == MarketRegime.WEAK_BEAR

def test_regime_engine_ranging_missing_data() -> None:
    engine = RegimeEngine()
    
    # Missing data should default to RANGING
    point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=None,
        ema_slow=Decimal("100"),
        rsi=Decimal("40"),
        atr=Decimal("2"),
    )
    series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=(point,))
    assert engine.evaluate(series, current_price=Decimal("80")) == MarketRegime.RANGING

    # Empty series
    empty_series = IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=())
    assert engine.evaluate(empty_series, current_price=Decimal("80")) == MarketRegime.RANGING
