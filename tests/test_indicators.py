"""
Tests for MarketPilot Indicators.
"""

import pytest
from datetime import datetime, UTC
from decimal import Decimal
from marketpilot.config.settings import IndicatorSettings
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.market import Kline
from marketpilot.core.enums import AssetType, Interval


@pytest.fixture
def indicator_settings() -> IndicatorSettings:
    return IndicatorSettings(
        ema_fast=2,
        ema_slow=3,
        rsi_period=2,
        macd_fast=2,
        macd_slow=3,
        macd_signal=2,
        atr_period=2,
        volume_sma_period=2
    )

def _kline(i: int, c: float, h: float, l: float, v: float) -> Kline:
    return Kline(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.fromtimestamp(1000000 + i * 3600, tz=UTC),
        open=str(c), # not used in indicators except open_time
        high=str(h),
        low=str(l),
        close=str(c),
        volume=str(v),
        turnover="0"
    )

def test_indicators_mathematical_precision(indicator_settings: IndicatorSettings) -> None:
    service = IndicatorService(indicator_settings)
    klines = [
        _kline(0, 100, 105, 95, 10),
        _kline(1, 102, 106, 96, 20), # ATR TR=11 (106-95), RSI gain=2, EMA fast start
        _kline(2, 101, 104, 100, 10), # ATR TR=4, RSI loss=1, EMA slow start, MACD slow start, Vol SMA
        _kline(3, 105, 110, 100, 30), # RSI starts here (requires 14 changes for 14, 2 for 2), wait, RSI initial is SMA of period. period=2 changes.
        _kline(4, 110, 115, 105, 40),
        _kline(5, 108, 110, 100, 20),
    ]

    # Mix order to test chronological sort
    mixed_klines = [klines[2], klines[0], klines[4], klines[5], klines[1], klines[3]]
    series = service.calculate(mixed_klines)
    
    assert len(series.points) == 6
    assert isinstance(series.points, tuple), "Points must be an immutable tuple"
    assert series.points[0].open_time == klines[0].open_time
    assert series.points[-1].open_time == klines[5].open_time

    # Point 0: No EMA
    assert series.points[0].ema_fast is None
    assert series.points[0].ema_slow is None

    # Point 1: EMA fast starts (SMA of first 2)
    assert series.points[1].ema_fast == Decimal("101")
    assert series.points[1].ema_slow is None

    # Point 2: EMA fast next step
    # multiplier = 2 / (2 + 1) = 2/3
    # next EMA fast = 101 * 2/3 + 101 * 1/3 = 101 (wait, close is 101, previous is 101)
    # EMA slow starts (SMA of first 3) = (100 + 102 + 101) / 3 = 101
    assert series.points[2].ema_fast == Decimal("101")
    assert series.points[2].ema_slow == Decimal("101")
    
    # MACD fast starts at index 1 (period 2), slow at index 2 (period 3)
    # MACD line at index 2 = ema_fast - ema_slow = 101 - 101 = 0
    # MACD signal needs 2 values of MACD line to start.
    assert series.points[2].macd_line == Decimal("0")
    assert series.points[2].macd_signal is None

    # Point 3: close=105
    # EMA fast = 105 * (2/3) + 101 * (1/3) = 70 + 33.666... = 103.6666...
    assert round(series.points[3].ema_fast, 4) == Decimal("103.6667")
    # MACD line at index 3: fast = 103.6666..., slow (3-period) = 105*(2/4) + 101*(2/4) = 52.5 + 50.5 = 103
    assert series.points[3].macd_line is not None
    # signal needs 2 points (index 2 and index 3)
    assert series.points[3].macd_signal is not None

def test_macd_signal_initialization_sma() -> None:
    settings = IndicatorSettings(macd_fast=2, macd_slow=3, macd_signal=3)
    service = IndicatorService(settings)
    
    # We need to trigger exactly the signal initialization
    # MACD slow starts at index 2. So MACD line starts at index 2.
    # MACD signal starts at index 4 (requires 3 MACD line values: idx 2, 3, 4)
    klines = [
        _kline(0, 100, 105, 95, 10),
        _kline(1, 102, 106, 96, 20),
        _kline(2, 101, 104, 100, 10), # MACD line 1 (0)
        _kline(3, 105, 110, 100, 30), # MACD line 2
        _kline(4, 110, 115, 105, 40), # MACD line 3 -> Signal starts (SMA of lines 1, 2, 3)
        _kline(5, 108, 110, 100, 20), # Signal uses EMA recurrence
    ]
    series = service.calculate(klines)
    assert series.points[2].macd_line is not None
    assert series.points[2].macd_signal is None
    assert series.points[3].macd_signal is None
    assert series.points[4].macd_signal is not None
    
    # Calculate expected
    m1 = series.points[2].macd_line
    m2 = series.points[3].macd_line
    m3 = series.points[4].macd_line
    expected_signal_sma = (m1 + m2 + m3) / Decimal("3")
    assert series.points[4].macd_signal == expected_signal_sma
    
    # Point 5 uses EMA recurrence
    mult = Decimal("2") / Decimal("4")
    m4 = series.points[5].macd_line
    expected_signal_ema = (m4 * mult) + (expected_signal_sma * (Decimal("1") - mult))
    assert series.points[5].macd_signal == expected_signal_ema

def test_rsi_explicit_warmup() -> None:
    # RSI 14 requires 14 price changes -> value at candle 15 (index 14)
    settings = IndicatorSettings(rsi_period=14)
    service = IndicatorService(settings)
    klines = [_kline(i, 100 + i, 101 + i, 99 + i, 10) for i in range(20)]
    
    series = service.calculate(klines)
    
    assert series.points[13].rsi is None
    assert series.points[14].rsi is not None
    assert series.points[15].rsi is not None

def test_atr_explicit_warmup() -> None:
    # ATR 14 requires 14 true ranges -> value at candle 14 (index 13)
    # TR calculation includes first candle as high - low.
    settings = IndicatorSettings(atr_period=14)
    service = IndicatorService(settings)
    klines = [_kline(i, 100, 105, 95, 10) for i in range(20)]
    
    series = service.calculate(klines)
    
    assert series.points[12].atr is None
    assert series.points[13].atr is not None
    assert series.points[14].atr is not None

def test_session_vwap() -> None:
    settings = IndicatorSettings()
    service = IndicatorService(settings)
    
    # 3 klines on day 1, 2 klines on day 2
    d1 = datetime(2023, 1, 1, tzinfo=UTC)
    d2 = datetime(2023, 1, 2, tzinfo=UTC)
    
    klines = [
        Kline(symbol="BTC", interval=Interval.H1, open_time=d1.replace(hour=1), open="100", high="110", low="90", close="100", volume="10", turnover="0"),
        Kline(symbol="BTC", interval=Interval.H1, open_time=d1.replace(hour=2), open="100", high="120", low="100", close="110", volume="20", turnover="0"),
        Kline(symbol="BTC", interval=Interval.H1, open_time=d1.replace(hour=3), open="110", high="130", low="110", close="120", volume="10", turnover="0"),
        
        # New day resets VWAP
        Kline(symbol="BTC", interval=Interval.H1, open_time=d2.replace(hour=1), open="120", high="140", low="120", close="130", volume="10", turnover="0"),
        Kline(symbol="BTC", interval=Interval.H1, open_time=d2.replace(hour=2), open="130", high="150", low="130", close="140", volume="20", turnover="0"),
    ]
    
    series = service.calculate(klines)
    
    # Day 1, point 0: typical = (110+90+100)/3 = 100. vol = 10. vwap = 100
    assert series.points[0].session_vwap == Decimal("100")
    
    # Day 1, point 1: typical = (120+100+110)/3 = 110. vol = 20. cum_vol = 30.
    # cum_price = 100*10 + 110*20 = 3200. vwap = 3200 / 30 = 106.6666...
    assert round(series.points[1].session_vwap, 4) == Decimal("106.6667")
    
    # Day 1, point 2: typical = (130+110+120)/3 = 120. vol = 10. cum_vol = 40.
    # cum_price = 3200 + 120*10 = 4400. vwap = 4400 / 40 = 110.
    assert series.points[2].session_vwap == Decimal("110")
    
    # Day 2, point 3: typical = (140+120+130)/3 = 130. vol = 10. (RESET)
    assert series.points[3].session_vwap == Decimal("130")
    
    # Day 2, point 4: typical = (150+130+140)/3 = 140. vol = 20. cum_vol = 30
    # cum_price = 130*10 + 140*20 = 4100. vwap = 4100 / 30 = 136.6666...
    assert round(series.points[4].session_vwap, 4) == Decimal("136.6667")

def test_mixed_symbols_raises() -> None:
    service = IndicatorService(IndicatorSettings())
    with pytest.raises(ValueError, match="All klines must share the same symbol"):
        service.calculate([
            _kline(0, 100, 105, 95, 10),
            Kline(symbol="ETHUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="1", volume="1", turnover="1")
        ])

def test_invalid_numerical_raises() -> None:
    service = IndicatorService(IndicatorSettings())
    bad_kline = Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="invalid", volume="1", turnover="1")
    klines = [bad_kline]
    with pytest.raises(ValueError, match="Invalid numerical data"):
        service.calculate(klines)

def test_non_finite_numerical_raises() -> None:
    service = IndicatorService(IndicatorSettings())
    bad_kline = Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="Infinity", volume="1", turnover="1")
    klines = [bad_kline]
    with pytest.raises(ValueError, match="is not finite"):
        service.calculate(klines)
        
    bad_kline2 = Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.now(tz=UTC), open="1", high="1", low="1", close="NaN", volume="1", turnover="1")
    with pytest.raises(ValueError, match="is not finite"):
        service.calculate([bad_kline2])
