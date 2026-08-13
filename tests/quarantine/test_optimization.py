"""Tests for historical parameter optimization."""

import datetime
from decimal import Decimal

import pytest

from marketpilot.config.settings import BacktestSettings, OptimizationSettings, StrategySettings
from marketpilot.core.enums import Interval
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.market import Kline
from marketpilot.optimization.service import OptimizationService
from marketpilot.risk.service import RiskManagerService


@pytest.fixture
def mock_klines() -> list[Kline]:
    """Generate 200 dummy klines."""
    klines = []
    base_time = datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    # create sine-wave like prices to trigger RSI bounds
    import math
    for i in range(200):
        # We need volatile prices so RSI will cross both 30 and 70 to trigger trades
        # 0..50 up, 50..100 down, 100..150 up, 150..200 down
        if i < 50 or (100 <= i < 150):
            price = 1000 + i * 10
        else:
            price = 1500 - (i % 50) * 10
            
        klines.append(
            Kline(
                symbol="BTCUSDT",
                interval=Interval.H1,
                open_time=base_time + datetime.timedelta(hours=i),
                open=str(price),
                high=str(price + 5),
                low=str(price - 5),
                close=str(price),
                volume="10",
                turnover="10000",
                is_closed=True
            )
        )
    return klines


@pytest.fixture
def opt_settings() -> OptimizationSettings:
    return OptimizationSettings(
        train_fraction=Decimal("0.70"),
        minimum_train_trades=0,  # Ensure no trades required so mock data works
        maximum_candidates=10,
        grid_rsi_long_min=[52, 55],
        grid_rsi_long_max=[70],
        grid_rsi_short_min=[30],
        grid_rsi_short_max=[45, 48]
    )


@pytest.fixture
def services(opt_settings: OptimizationSettings) -> tuple[IndicatorService, RiskManagerService, OptimizationService]:
    from marketpilot.config.settings import IndicatorSettings, RiskSettings
    
    ind_service = IndicatorService(IndicatorSettings())
    risk_service = RiskManagerService(RiskSettings())
    baseline = StrategySettings(rsi_long_min=55, rsi_long_max=70, rsi_short_min=30, rsi_short_max=45)
    
    opt_service = OptimizationService(
        settings=opt_settings,
        indicator_service=ind_service,
        risk_service=risk_service,
        baseline_strategy_settings=baseline,
        backtest_settings_factory=BacktestSettings,
        backtest_settings_kwargs={"initial_equity": Decimal("10000")}
    )
    return ind_service, risk_service, opt_service


def test_optimization_empty_klines(services: tuple[IndicatorService, RiskManagerService, OptimizationService]) -> None:
    _, _, opt_service = services
    with pytest.raises(ValueError, match="No klines provided"):
        opt_service.optimize([])


def test_optimization_insufficient_klines(services: tuple[IndicatorService, RiskManagerService, OptimizationService]) -> None:
    _, _, opt_service = services
    base_time = datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
    # Provide only 40 klines. Split check needs 50 each.
    klines = [
        Kline(symbol="BTCUSDT", interval=Interval.H1, open_time=base_time + datetime.timedelta(hours=i),
              open="1000", high="1000", low="1000", close="1000", volume="10", turnover="10000", is_closed=True)
        for i in range(40)
    ]
    with pytest.raises(ValueError, match="Insufficient klines for split"):
        opt_service.optimize(klines)


def test_optimization_candidate_deduplication(services: tuple[IndicatorService, RiskManagerService, OptimizationService], mock_klines: list[Kline]) -> None:
    _, _, opt_service = services
    result = opt_service.optimize(mock_klines)
    
    # Grid: l_min(52,55) x l_max(70) x s_min(30) x s_max(45,48) = 4 candidates.
    # Baseline: (55, 70, 30, 45).
    # Since baseline is (55, 70, 30, 45) which is one of the grid items, it should be deduplicated
    # and the label 'baseline' should be kept.
    assert len(result.candidates) == 4
    
    baseline_found = False
    for c in result.candidates:
        if c.candidate.label == "baseline":
            baseline_found = True
            assert c.candidate.strategy_settings.rsi_long_min == 55
            assert c.candidate.strategy_settings.rsi_long_max == 70
            assert c.candidate.strategy_settings.rsi_short_min == 30
            assert c.candidate.strategy_settings.rsi_short_max == 45
    
    assert baseline_found, "Baseline candidate must be preserved and deduplicated."


def test_optimization_ineligible_candidates(services: tuple[IndicatorService, RiskManagerService, OptimizationService], mock_klines: list[Kline]) -> None:
    _, _, opt_service = services
    opt_service._settings.minimum_train_trades = 9999  # Nothing will meet this
    
    result = opt_service.optimize(mock_klines)
    
    assert result.best_candidate is None
    for res in result.candidates:
        assert not res.is_eligible
        assert res.train_objective is None
        assert res.val_metrics is None
        assert "Only" in str(res.rejection_reason)


def test_optimization_maximum_candidates_exceeded(services: tuple[IndicatorService, RiskManagerService, OptimizationService], mock_klines: list[Kline]) -> None:
    _, _, opt_service = services
    opt_service._settings.maximum_candidates = 2  # Our grid has 4
    
    with pytest.raises(ValueError, match="exceeds the maximum"):
        opt_service.optimize(mock_klines)


def test_optimization_sorting_and_validation_independence(
    services: tuple[IndicatorService, RiskManagerService, OptimizationService],
    mock_klines: list[Kline]
) -> None:
    _, _, opt_service = services
    
    result_normal = opt_service.optimize(mock_klines)
    assert result_normal.best_candidate is not None
    winner_label = result_normal.best_candidate.candidate.label
    
    # Verify deterministic sort: train_obj descending, max_drawdown ascending, label ascending
    eligible = [c for c in result_normal.candidates if c.is_eligible]
    for i in range(len(eligible) - 1):
        c1 = eligible[i]
        c2 = eligible[i+1]
        
        # If train_obj is same, drawdown must be <=
        if c1.train_objective == c2.train_objective:
            assert float(c1.train_metrics.max_drawdown_fraction) <= float(c2.train_metrics.max_drawdown_fraction) # type: ignore
    
    # Mutate validation candles, append 50 more random candles
    klines_mutated = list(mock_klines)
    base_time = mock_klines[-1].open_time
    for i in range(1, 51):
        klines_mutated.append(Kline(
            symbol="BTCUSDT", interval=Interval.H1, open_time=base_time + datetime.timedelta(hours=i),
            open="100", high="100", low="100", close="100", volume="10", turnover="10", is_closed=True
        ))
        
    result_mutated = opt_service.optimize(klines_mutated)
    
    # Winner must be exactly the same, because it depends ONLY on training split
    assert result_mutated.best_candidate is not None
    assert result_mutated.best_candidate.candidate.label == winner_label
    
    # Train metrics for the winner must be identical
    w1 = result_normal.best_candidate.train_metrics
    w2 = result_mutated.best_candidate.train_metrics
    assert w1 == w2
