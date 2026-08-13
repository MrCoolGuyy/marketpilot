"""
Tests for historical backtesting engine.
"""

from __future__ import annotations

import datetime
import random
from decimal import Decimal

import pytest

from marketpilot.backtest.engine import BacktestEngine
from marketpilot.config.settings import BacktestSettings, IndicatorSettings, RiskSettings, StrategySettings
from marketpilot.core.enums import Interval
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.market import Kline
from marketpilot.models.strategy import SignalDirection
from marketpilot.risk.service import RiskManagerService
from marketpilot.strategy.service import StrategyService


@pytest.fixture
def backtest_settings() -> BacktestSettings:
    return BacktestSettings(
        initial_equity=Decimal("10000"),
        leverage=5,
        taker_fee_fraction=Decimal("0.001"),
        slippage_bps=Decimal("10"),
    )


@pytest.fixture
def services(backtest_settings: BacktestSettings) -> tuple[IndicatorService, StrategyService, RiskManagerService]:
    return (
        IndicatorService(IndicatorSettings()),
        StrategyService(StrategySettings()),
        RiskManagerService(RiskSettings()),
    )


def test_backtest_engine_basic_lifecycle(
    backtest_settings: BacktestSettings,
    services: tuple[IndicatorService, StrategyService, RiskManagerService]
) -> None:
    """Test engine lifecycle with some mocked klines."""
    indicator_service, strategy_service, risk_service = services
    engine = BacktestEngine(backtest_settings, indicator_service, strategy_service, risk_service)

    klines = []
    base_time = datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    
    price = Decimal("1000")
    for i in range(50):
        o = price
        h = price + Decimal("50")
        l = price - Decimal("10")
        price += Decimal("20")
        c = price
        
        klines.append(Kline(
            symbol="BTCUSDT",
            interval=Interval.H1,
            open_time=base_time + datetime.timedelta(hours=i),
            open=str(o),
            high=str(h),
            low=str(l),
            close=str(c),
            volume="10",
            turnover="10000",
            is_closed=True
        ))

    result = engine.run(klines)
    
    assert result.symbol == "BTCUSDT"
    assert result.start_time == base_time
    # Initial + 50 candles
    assert len(result.equity_curve) == 51
    assert result.metrics.starting_equity == Decimal("10000")
    
    if len(result.trades) > 0:
        trade = result.trades[0]
        assert trade.signal_time < trade.entry_time
        assert trade.entry_time <= trade.exit_time
        assert trade.direction == SignalDirection.LONG


def test_backtest_engine_stop_target_priority(
    backtest_settings: BacktestSettings,
    services: tuple[IndicatorService, StrategyService, RiskManagerService]
) -> None:
    """Test that when stop-loss and take-profit are both hit in one candle, stop-loss wins."""
    indicator_service, strategy_service, risk_service = services
    
    original_evaluate = strategy_service.evaluate
    def mock_evaluate(series: object) -> object:
        from marketpilot.models.strategy import StrategySignal
        if len(series.points) == 60: # type: ignore
            return StrategySignal(
                symbol="BTCUSDT",
                interval=Interval.H1,
                open_time=series.points[-1].open_time, # type: ignore
                direction=SignalDirection.LONG,
                score=Decimal("100"),
                reasons=("mocked",)
            )
        return original_evaluate(series)
        
    strategy_service.evaluate = mock_evaluate # type: ignore
    
    original_assess = risk_service.assess
    def mock_assess(signal: object, entry_price: Decimal, atr: Decimal, account_equity: Decimal) -> object:
        from marketpilot.models.risk import RiskAssessment
        if signal.score == Decimal("100"): # type: ignore
            return RiskAssessment(
                symbol="BTCUSDT",
                interval=Interval.H1,
                open_time=signal.open_time, # type: ignore
                direction=SignalDirection.LONG,
                eligible_for_paper_trading=True,
                entry_price=entry_price,
                stop_loss=entry_price - Decimal("50"),
                take_profit=entry_price + Decimal("50"),
                stop_distance=Decimal("50"),
                reward_risk_ratio=Decimal("1.0"),
                risk_budget=Decimal("100"),
                theoretical_quantity=Decimal("1.0"),
                theoretical_notional=entry_price,
                reasons=("mocked",)
            )
        return original_assess(signal, entry_price, atr, account_equity) # type: ignore
        
    risk_service.assess = mock_assess # type: ignore

    engine = BacktestEngine(backtest_settings, indicator_service, strategy_service, risk_service)

    klines = []
    base_time = datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    for i in range(60):
        klines.append(Kline(
            symbol="BTCUSDT", interval=Interval.H1,
            open_time=base_time + datetime.timedelta(hours=i),
            open="1000", high="1000", low="1000", close="1000",
            volume="10", turnover="10000", is_closed=True
        ))
        
    # Candle 60 closes -> signal is LONG
    klines.append(Kline(
        symbol="BTCUSDT", interval=Interval.H1,
        open_time=base_time + datetime.timedelta(hours=60),
        open="1000", high="1000", low="1000", close="1000",
        volume="10", turnover="10000", is_closed=True
    ))
    
    # Candle 61 opens -> position enters. And intrabar hits BOTH the stop-loss (950) and take-profit (1050)
    klines.append(Kline(
        symbol="BTCUSDT", interval=Interval.H1,
        open_time=base_time + datetime.timedelta(hours=61),
        open="1000", high="1060", low="940", close="1200", # Close is 1200 to test equity timing!
        volume="10", turnover="10000", is_closed=True
    ))

    result = engine.run(klines)
    
    assert len(result.trades) == 1
    trade = result.trades[0]
    
    # Stop loss should win because of conservative rule
    assert trade.exit_reason == "stop_loss"
    
    # The equity curve for candle 61 MUST reflect the stop_loss hit, NOT the 1200 close MTM.
    # Entry price is 1000 (plus slippage). Stop is 950 (minus slippage).
    # Realized loss is roughly ~ -50 * qty.
    # The MTM of 1200 would have been ~ +200.
    final_equity = result.equity_curve[-1]
    assert final_equity < Decimal("10000"), "Equity must be lower because stop-loss was realized, despite high close"
    assert result.metrics.ending_equity == final_equity


def test_backtest_metrics_calculation(
    backtest_settings: BacktestSettings,
    services: tuple[IndicatorService, StrategyService, RiskManagerService]
) -> None:
    """Test metrics logic for zero loss / no trade scenarios."""
    indicator_service, strategy_service, risk_service = services
    engine = BacktestEngine(backtest_settings, indicator_service, strategy_service, risk_service)
    
    with pytest.raises(ValueError, match="No klines"):
        engine.run([])
        
    klines = [
        Kline(
            symbol="BTCUSDT", interval=Interval.H1,
            open_time=datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc),
            open="1000", high="1000", low="1000", close="1000",
            volume="10", turnover="10000", is_closed=True
        )
    ]
    result = engine.run(klines)
    assert result.metrics.trade_count == 0
    assert result.metrics.win_rate is None
    assert result.metrics.profit_factor is None
    assert result.metrics.total_return_fraction == Decimal("0")
    assert result.metrics.max_drawdown_fraction == Decimal("0")


def test_backtest_engine_validation(
    backtest_settings: BacktestSettings,
    services: tuple[IndicatorService, StrategyService, RiskManagerService]
) -> None:
    """Test engine validation: mixed symbols, open klines, unsorted input."""
    indicator_service, strategy_service, risk_service = services
    engine = BacktestEngine(backtest_settings, indicator_service, strategy_service, risk_service)
    
    base_time = datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    klines = [
        Kline(
            symbol="BTCUSDT", interval=Interval.H1,
            open_time=base_time,
            open="1000", high="1000", low="1000", close="1000",
            volume="10", turnover="10000", is_closed=True
        ),
        Kline(
            symbol="ETHUSDT", interval=Interval.H1, # MIXED SYMBOL
            open_time=base_time + datetime.timedelta(hours=1),
            open="100", high="100", low="100", close="100",
            volume="10", turnover="10000", is_closed=True
        )
    ]
    with pytest.raises(ValueError, match="Mixed symbols"):
        engine.run(klines)
        
    klines[1] = Kline(
        symbol="BTCUSDT", interval=Interval.H1,
        open_time=base_time + datetime.timedelta(hours=1),
        open="1000", high="1000", low="1000", close="1000",
        volume="10", turnover="10000", is_closed=False # OPEN KLINE
    )
    with pytest.raises(ValueError, match="Open klines"):
        engine.run(klines)

    # Test sorting
    klines_sorted = []
    for i in range(10):
        klines_sorted.append(Kline(
            symbol="BTCUSDT", interval=Interval.H1,
            open_time=base_time + datetime.timedelta(hours=i),
            open="1000", high="1000", low="1000", close="1000",
            volume="10", turnover="10000", is_closed=True
        ))
        
    klines_shuffled = klines_sorted.copy()
    random.shuffle(klines_shuffled)
    
    # Engine must not mutate caller's list
    original_order = [k.open_time for k in klines_shuffled]
    result = engine.run(klines_shuffled)
    assert [k.open_time for k in klines_shuffled] == original_order
    
    assert result.start_time == base_time
    assert result.end_time == base_time + datetime.timedelta(hours=9)
    assert len(result.equity_curve) == 11
