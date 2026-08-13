"""Tests for Strategy Engine."""

from datetime import datetime, UTC
from decimal import Decimal
import pytest

from marketpilot.config.settings import StrategySettings
from marketpilot.engines.strategy_engine import StrategyEngine
from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
from marketpilot.models.regime import MarketRegime
from marketpilot.models.scanner import InstrumentSnapshot
from marketpilot.models.strategy import SignalDirection
from marketpilot.core.enums import AssetType, Interval

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
    
    snap = InstrumentSnapshot(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        last_price=Decimal("101"),
        liquidity_turnover_24h=Decimal("1000000"),
        volume_24h=Decimal("20"),
        spread_bps=Decimal("10"),
        atr_percent=Decimal("0.02"),
        momentum_24h=Decimal("0.01"),
        trend_strength=Decimal("0.2"),
        trend_age_candles=10,
        market_quality=Decimal("80")
    )
    
    # Eval with decision_id
    all_results, best_result, metadata = engine.evaluate(series, MarketRegime.TRENDING_BULL, snap, decision_id="test-123")
    
    assert best_result is not None
    assert best_result.strategy_name == "EMA Pullback"
    assert best_result.signal == SignalDirection.LONG
    assert best_result.reason_code == "BULL_EMA_TOUCH"
    
    assert best_result.candidate_trade is not None
    assert best_result.candidate_trade.stop_loss == Decimal("98.0000")
    assert best_result.candidate_trade.take_profit == Decimal("110.0000")
    
    assert best_result.candidate_trade.expected_rr >= Decimal("2.0")
    assert "overall_score" in best_result.metrics
    
    assert metadata.decision_id == "test-123"
    assert len(all_results) == 4
