"""Tests for Research Journal."""

import pytest
from datetime import datetime, UTC, timedelta
from decimal import Decimal

from marketpilot.config.settings import AppSettings, StrategySettings, RiskSettings, IndicatorSettings
from marketpilot.models.market import Kline
from marketpilot.models.research import ResearchObservation, ResearchOutcome
from marketpilot.models.strategy import SignalDirection
from marketpilot.research.service import ResearchService
from marketpilot.research.store import ResearchStore

@pytest.fixture
def clean_store(tmp_path):
    store = ResearchStore(data_dir=tmp_path)
    return store

@pytest.fixture
def mock_settings():
    return AppSettings(
        strategy=StrategySettings(rsi_lower=30, rsi_upper=70),
        risk=RiskSettings(max_position_size=Decimal("1.0"), max_risk_per_trade=Decimal("0.02"), atr_multiplier=Decimal("2.0")),
        indicators=IndicatorSettings()
    )

def test_research_store_decimal_serialization(clean_store):
    obs = ResearchObservation(
        symbol="BTCUSDT",
        interval="60",
        signal_time=datetime(2025, 1, 1, 10, tzinfo=UTC),
        capture_time=datetime.now(tz=UTC),
        direction=SignalDirection.LONG,
        entry_price=Decimal("50000.5"),
        stop_loss=Decimal("49000.1"),
        take_profit=Decimal("52000.9"),
        theoretical_quantity=Decimal("0.5"),
        strategy_settings={},
        risk_settings={},
        status=ResearchOutcome.OPEN
    )
    
    clean_store.save_observations([obs])
    loaded = clean_store.load_observations()
    
    assert len(loaded) == 1
    assert loaded[0].entry_price == Decimal("50000.5")
    assert isinstance(loaded[0].entry_price, Decimal)

def test_no_lookahead_and_duplication(clean_store, mock_settings, monkeypatch):
    service = ResearchService(mock_settings)
    service.store = clean_store
    
    # We mock strategy service to always return an eligible LONG signal
    from marketpilot.models.strategy import StrategySignal
    
    class MockStrategy:
        def __init__(self, *args, **kwargs): pass
        def evaluate(self, series):
            return StrategySignal(
                symbol="BTCUSDT",
                interval="60",
                open_time=datetime(2025, 1, 1, 10, tzinfo=UTC),
                direction=SignalDirection.LONG,
                score=Decimal("0"),
                reasons=[]
            )
            
    class MockRisk:
        def __init__(self, *args, **kwargs): pass
        def evaluate(self, *args, **kwargs):
            from marketpilot.models.risk import RiskAssessment
            return RiskAssessment(
                symbol="BTCUSDT", interval="60", open_time=datetime(2025, 1, 1, 10, tzinfo=UTC),
                direction=SignalDirection.LONG, eligible_for_paper_trading=True,
                reasons=[],
                stop_loss=Decimal("49000"), take_profit=Decimal("52000"),
                theoretical_quantity=Decimal("1"), theoretical_notional=Decimal("50000"),
                reward_risk_ratio=Decimal("2")
            )
            
    monkeypatch.setattr("marketpilot.research.service.StrategyService", MockStrategy)
    monkeypatch.setattr("marketpilot.research.service.RiskManagerService", MockRisk)
    
    # Create valid klines (must be closed)
    klines = [
        Kline(symbol="BTCUSDT", interval="60", open_time=datetime(2025, 1, 1, 9, tzinfo=UTC), open="50000", high="50000", low="50000", close="50000", volume="1", turnover="1", is_closed=True),
        Kline(symbol="BTCUSDT", interval="60", open_time=datetime(2025, 1, 1, 10, tzinfo=UTC), open="50000", high="50000", low="50000", close="50000", volume="1", turnover="1", is_closed=True)
    ]
    
    obs = service.capture(klines, Decimal("10000"))
    assert obs is not None
    assert obs.status == ResearchOutcome.OPEN
    assert obs.signal_time == datetime(2025, 1, 1, 10, tzinfo=UTC)
    
    # Duplicate capture should return None
    obs2 = service.capture(klines, Decimal("10000"))
    assert obs2 is None

def test_stop_first_evaluation(clean_store, mock_settings):
    service = ResearchService(mock_settings)
    service.store = clean_store
    
    obs = ResearchObservation(
        symbol="BTCUSDT",
        interval="60",
        signal_time=datetime(2025, 1, 1, 10, tzinfo=UTC),
        capture_time=datetime.now(tz=UTC),
        direction=SignalDirection.LONG,
        entry_price=Decimal("50000"),
        stop_loss=Decimal("49000"),
        take_profit=Decimal("52000"),
        theoretical_quantity=Decimal("1"),
        strategy_settings={},
        risk_settings={},
        status=ResearchOutcome.OPEN
    )
    clean_store.save_observations([obs])
    
    # Forward kline hits BOTH stop and target in the same candle
    # Expected behavior: STOP LOSS always wins (conservative)
    forward_klines = [
        Kline(symbol="BTCUSDT", interval="60", open_time=datetime(2025, 1, 1, 11, tzinfo=UTC), open="50000", high="53000", low="48000", close="50000", volume="1", turnover="1", is_closed=True)
    ]
    
    resolved = service.evaluate(forward_klines)
    assert resolved == 1
    
    loaded = clean_store.load_observations()[0]
    assert loaded.status == ResearchOutcome.STOP_LOSS
    assert loaded.realized_r == Decimal("-1")

def test_small_sample_report(clean_store, mock_settings):
    service = ResearchService(mock_settings)
    service.store = clean_store
    
    report = service.generate_report()
    assert report.total_observations == 0
    assert report.resolved_count == 0
    assert report.win_rate is None
    assert report.expectancy is None
    
    obs = ResearchObservation(
        symbol="BTCUSDT", interval="60", signal_time=datetime(2025, 1, 1, 10, tzinfo=UTC), capture_time=datetime.now(tz=UTC),
        direction=SignalDirection.LONG, entry_price=Decimal("50000"), stop_loss=Decimal("49000"), take_profit=Decimal("52000"), theoretical_quantity=Decimal("1"),
        strategy_settings={}, risk_settings={}, status=ResearchOutcome.OPEN
    )
    clean_store.save_observations([obs])
    
    report2 = service.generate_report()
    assert report2.open_count == 1
    assert report2.resolved_count == 0
    assert report2.win_rate is None
