import pytest
import time
from decimal import Decimal
from datetime import datetime
from marketpilot.core.enums import AssetType, Interval
from marketpilot.models.market import Kline, Ticker
from marketpilot.models.market_data import RawMarketData
from marketpilot.models.causal import ClosedInstrumentSnapshot, SnapshotBuildOutcome
from marketpilot.scanner.snapshot_builder import InstrumentSnapshotBuilder
from marketpilot.core.time import MarketObservationClock, CandleBoundaryResolver
from unittest.mock import MagicMock

def test_causal_snapshot_builder():
    indicator_mock = MagicMock()
    indicator_mock.calculate.return_value = MagicMock(points=[])
    builder = InstrumentSnapshotBuilder(indicator_mock)
    
    # Create an old closed candle and a new open candle
    now = time.time()
    old_time = now - 7200
    new_time = now - 60
    
    k1 = Kline(
        symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.fromtimestamp(old_time),
        open="100", high="110", low="90", close="105", volume="10", turnover="1000", is_closed=True
    )
    k2 = Kline(
        symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.fromtimestamp(new_time),
        open="105", high="120", low="100", close="115", volume="5", turnover="550", is_closed=False
    )
    ticker = Ticker(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="115", bid_price="114", ask_price="116",
        high_24h="120", low_24h="90", price_change_percent_24h="5", volume_24h="100", turnover_24h="10000", timestamp=datetime.fromtimestamp(now)
    )
    raw = RawMarketData(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, ticker=ticker, klines=[k1, k2], timestamp=now
    )
    
    clock = MarketObservationClock(observed_at=now, time_source="TEST", provenance="local")
    result = builder.build_causal(raw, clock)
    
    assert result.outcome == SnapshotBuildOutcome.BUILT
    causal = result.snapshot
    assert causal is not None
    assert isinstance(causal, ClosedInstrumentSnapshot)
    # The facts should come from k1 (the closed one), not k2 (the forming one)
    assert causal.facts.close == Decimal("105")
    assert causal.facts.volume == Decimal("10")
    
    # Test future leakage protection
    # If the closed candle actually closed in the future (malformed data or clock skew)
    k1_future = Kline(
        symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.fromtimestamp(now + 100),
        open="100", high="110", low="90", close="105", volume="10", turnover="1000", is_closed=True
    )
    raw_future = RawMarketData(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, ticker=ticker, klines=[k1_future], timestamp=now
    )
    
    result_future = builder.build_causal(raw_future, clock)
    assert result_future.outcome == SnapshotBuildOutcome.NO_CLOSED_CANDLES

def test_causal_non_monotonic_history():
    indicator_mock = MagicMock()
    indicator_mock.calculate.return_value = MagicMock(points=[])
    builder = InstrumentSnapshotBuilder(indicator_mock)
    now = time.time()
    
    k1 = Kline(
        symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.fromtimestamp(now - 7200),
        open="100", high="110", low="90", close="105", volume="10", turnover="1000", is_closed=True
    )
    k2 = Kline(
        symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.fromtimestamp(now - 7200), # duplicate open time
        open="105", high="110", low="100", close="108", volume="10", turnover="1000", is_closed=True
    )
    ticker = Ticker(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="115", bid_price="114", ask_price="116",
        high_24h="120", low_24h="90", price_change_percent_24h="5", volume_24h="100", turnover_24h="10000", timestamp=datetime.fromtimestamp(now)
    )
    
    raw = RawMarketData(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, ticker=ticker, klines=[k2, k1], timestamp=now
    )
    
    clock = MarketObservationClock(observed_at=now, time_source="TEST", provenance="local")
    result = builder.build_causal(raw, clock)
    assert result.outcome == SnapshotBuildOutcome.NON_MONOTONIC_HISTORY
    assert result.snapshot is None

def test_feature_provenance_within_causal_boundary():
    indicator_mock = MagicMock()
    indicator_mock.calculate.return_value = MagicMock(points=[])
    builder = InstrumentSnapshotBuilder(indicator_mock)
    now = time.time()
    
    k1 = Kline(
        symbol="BTCUSDT", interval=Interval.H1, open_time=datetime.fromtimestamp(now - 7200),
        open="100", high="110", low="90", close="105", volume="10", turnover="1000", is_closed=True
    )
    ticker = Ticker(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="115", bid_price="114", ask_price="116",
        high_24h="120", low_24h="90", price_change_percent_24h="5", volume_24h="100", turnover_24h="10000", timestamp=datetime.fromtimestamp(now)
    )
    raw = RawMarketData(
        symbol="BTCUSDT", asset_type=AssetType.LINEAR, ticker=ticker, klines=[k1], timestamp=now
    )
    
    clock = MarketObservationClock(observed_at=now, time_source="TEST", provenance="local")
    result = builder.build_causal(raw, clock)
    
    assert result.outcome == SnapshotBuildOutcome.BUILT
    causal = result.snapshot
    assert causal is not None
    assert causal.creation_timestamp >= causal.candle_close_time
    assert causal.candle_close_time <= time.time()
    assert causal.facts.close == Decimal("105")

def test_interval_boundaries():
    t_base = 1700000000 # Just an arbitrary timestamp
    
    # Minute
    assert CandleBoundaryResolver.get_close_time(t_base, Interval.M1) == t_base + 60
    assert CandleBoundaryResolver.get_close_time(t_base, Interval.M5) == t_base + 300
    assert CandleBoundaryResolver.get_close_time(t_base, Interval.H1) == t_base + 3600
    assert CandleBoundaryResolver.get_close_time(t_base, Interval.D1) == t_base + 86400
    assert CandleBoundaryResolver.get_close_time(t_base, Interval.W1) == t_base + (7 * 86400)
    
    # Month boundary (February 2024, leap year)
    # 2024-02-01 00:00:00 UTC = 1706745600
    t_feb = 1706745600
    feb_days = 29
    assert CandleBoundaryResolver.get_close_time(t_feb, Interval.MN1) == t_feb + (feb_days * 86400)

def test_exact_finality_edge():
    open_time = 1700000000
    interval = Interval.H1
    close_boundary = open_time + 3600
    
    clock_forming = MarketObservationClock(observed_at=close_boundary - 0.1, time_source="TEST", provenance="")
    assert CandleBoundaryResolver.is_closed(open_time, interval, clock_forming) is False
    
    clock_closed = MarketObservationClock(observed_at=close_boundary, time_source="TEST", provenance="")
    assert CandleBoundaryResolver.is_closed(open_time, interval, clock_closed) is True
    
def test_rest_ws_consistency():
    # A candle explicitly confirmed via WS should be closed regardless of time.
    # Our builder handles WS `confirm` property dynamically if added.
    pass

