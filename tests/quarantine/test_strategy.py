"""
Tests for MarketPilot Strategy module.
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from marketpilot.config.settings import StrategySettings
from marketpilot.core.enums import Interval
from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
from marketpilot.models.strategy import SignalDirection
from marketpilot.strategy.service import StrategyService


@pytest.fixture
def strategy_settings() -> StrategySettings:
    return StrategySettings(
        rsi_long_min=55,
        rsi_long_max=70,
        rsi_short_min=30,
        rsi_short_max=45,
    )


def _make_series(
    ema_fast: str | None = "50",
    ema_slow: str | None = "40",
    macd_line: str | None = "5",
    macd_signal: str | None = "2",
    macd_hist: str | None = "3",
    rsi: str | None = "60"
) -> IndicatorSeries:
    point = IndicatorPoint(
        open_time=datetime.now(tz=UTC),
        ema_fast=Decimal(ema_fast) if ema_fast else None,
        ema_slow=Decimal(ema_slow) if ema_slow else None,
        rsi=Decimal(rsi) if rsi else None,
        macd_line=Decimal(macd_line) if macd_line else None,
        macd_signal=Decimal(macd_signal) if macd_signal else None,
        macd_histogram=Decimal(macd_hist) if macd_hist else None,
        atr=Decimal("10"),
        volume_sma=Decimal("100")
    )
    return IndicatorSeries(symbol="BTCUSDT", interval=Interval.H1, points=tuple([point]))


def test_strategy_long_signal(strategy_settings: StrategySettings) -> None:
    service = StrategyService(strategy_settings)
    # Meets all LONG criteria
    series = _make_series(ema_fast="50", ema_slow="40", macd_line="5", macd_signal="2", macd_hist="3", rsi="60")
    signal = service.evaluate(series)

    assert signal.direction == SignalDirection.LONG
    assert signal.score == Decimal("100")
    assert signal.reasons == ("long_conditions_met",)


def test_strategy_short_signal(strategy_settings: StrategySettings) -> None:
    service = StrategyService(strategy_settings)
    # Meets all SHORT criteria
    series = _make_series(ema_fast="40", ema_slow="50", macd_line="-5", macd_signal="-2", macd_hist="-3", rsi="40")
    signal = service.evaluate(series)

    assert signal.direction == SignalDirection.SHORT
    assert signal.score == Decimal("100")
    assert signal.reasons == ("short_conditions_met",)


def test_strategy_neutral_incomplete_data(strategy_settings: StrategySettings) -> None:
    service = StrategyService(strategy_settings)
    # Missing RSI
    series = _make_series(rsi=None)
    signal = service.evaluate(series)

    assert signal.direction == SignalDirection.NEUTRAL
    assert signal.score == Decimal("0")
    assert signal.reasons == ("insufficient_indicator_data",)


def test_strategy_neutral_conflicting(strategy_settings: StrategySettings) -> None:
    service = StrategyService(strategy_settings)
    # Meets some LONG and some SHORT, but not all of either
    series = _make_series(ema_fast="50", ema_slow="40", macd_line="-5", macd_signal="-2", macd_hist="-3", rsi="50")
    signal = service.evaluate(series)

    assert signal.direction == SignalDirection.NEUTRAL
    assert signal.score == Decimal("0")
    # It should contain failure reasons for both sides
    assert "macd_line_not_bullish" in signal.reasons
    assert "macd_hist_not_positive" in signal.reasons
    assert "rsi_not_in_long_range" in signal.reasons
    assert "ema_not_bearish" in signal.reasons
    assert "rsi_not_in_short_range" in signal.reasons


def test_strategy_settings_validation_overlap() -> None:
    with pytest.raises(ValueError, match="must not overlap"):
        StrategySettings(rsi_long_min=50, rsi_long_max=70, rsi_short_min=40, rsi_short_max=55)


def test_strategy_settings_validation_invalid_range() -> None:
    with pytest.raises(ValueError, match="must be <="):
        StrategySettings(rsi_long_min=70, rsi_long_max=50)
