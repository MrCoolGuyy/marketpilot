"""
Tests for MarketPilot Risk Manager module.
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from marketpilot.config.settings import RiskSettings
from marketpilot.core.enums import Interval
from marketpilot.models.risk import RiskAssessment
from marketpilot.models.strategy import SignalDirection, StrategySignal
from marketpilot.risk.service import RiskManagerService


@pytest.fixture
def risk_settings() -> RiskSettings:
    return RiskSettings(
        risk_per_trade_fraction=Decimal("0.01"),
        atr_stop_multiplier=Decimal("1.5"),
        minimum_reward_risk=Decimal("2.0"),
        maximum_atr_fraction=Decimal("0.05")
    )


def _make_signal(
    direction: SignalDirection = SignalDirection.LONG,
    score: str = "100"
) -> StrategySignal:
    return StrategySignal(
        symbol="BTCUSDT",
        interval=Interval.H1,
        open_time=datetime.now(tz=UTC),
        direction=direction,
        score=Decimal(score),
        reasons=("mock_reason",)
    )


def test_risk_manager_long_success(risk_settings: RiskSettings) -> None:
    service = RiskManagerService(risk_settings)
    signal = _make_signal(SignalDirection.LONG, "100")
    
    # entry: 1000, ATR: 20, equity: 10000
    # stop_dist = 20 * 1.5 = 30
    # risk_budget = 10000 * 0.01 = 100
    # qty = 100 / 30 = 3.3333333333...
    # notional = 3.333333... * 1000
    # stop_loss = 1000 - 30 = 970
    # take_profit = 1000 + 30 * 2.0 = 1060
    assessment = service.assess(signal, Decimal("1000"), Decimal("20"), Decimal("10000"))
    
    assert assessment.eligible_for_paper_trading is True
    assert assessment.stop_loss == Decimal("970")
    assert assessment.take_profit == Decimal("1060")
    assert assessment.stop_distance == Decimal("30")
    assert assessment.reward_risk_ratio == Decimal("2.0")
    assert assessment.risk_budget == Decimal("100")
    assert assessment.theoretical_quantity == Decimal("100") / Decimal("30")
    assert assessment.theoretical_notional == (Decimal("100") / Decimal("30")) * Decimal("1000")


def test_risk_manager_short_success(risk_settings: RiskSettings) -> None:
    service = RiskManagerService(risk_settings)
    signal = _make_signal(SignalDirection.SHORT, "100")
    
    assessment = service.assess(signal, Decimal("1000"), Decimal("20"), Decimal("10000"))
    
    assert assessment.eligible_for_paper_trading is True
    assert assessment.stop_loss == Decimal("1030")
    assert assessment.take_profit == Decimal("940")
    assert assessment.stop_distance == Decimal("30")


def test_risk_manager_rejects_neutral_and_low_score(risk_settings: RiskSettings) -> None:
    service = RiskManagerService(risk_settings)
    
    signal1 = _make_signal(SignalDirection.NEUTRAL, "100")
    assessment1 = service.assess(signal1, Decimal("1000"), Decimal("20"), Decimal("10000"))
    assert assessment1.eligible_for_paper_trading is False
    assert assessment1.entry_price is None
    assert assessment1.stop_loss is None
    assert "strategy_signal_not_actionable" in assessment1.reasons
    
    signal2 = _make_signal(SignalDirection.LONG, "99")
    assessment2 = service.assess(signal2, Decimal("1000"), Decimal("20"), Decimal("10000"))
    assert assessment2.eligible_for_paper_trading is False
    assert assessment2.entry_price is None


def test_risk_manager_rejects_excessive_volatility(risk_settings: RiskSettings) -> None:
    service = RiskManagerService(risk_settings)
    signal = _make_signal(SignalDirection.LONG, "100")
    
    # max ATR fraction is 0.05. ATR 60 / 1000 = 0.06 > 0.05.
    assessment = service.assess(signal, Decimal("1000"), Decimal("60"), Decimal("10000"))
    assert assessment.eligible_for_paper_trading is False
    assert "excessive_volatility" in assessment.reasons
    assert assessment.take_profit is None


def test_risk_manager_rejects_invalid_inputs(risk_settings: RiskSettings) -> None:
    service = RiskManagerService(risk_settings)
    signal = _make_signal(SignalDirection.LONG, "100")
    
    # 0 entry price
    assessment1 = service.assess(signal, Decimal("0"), Decimal("20"), Decimal("10000"))
    assert assessment1.eligible_for_paper_trading is False
    assert "invalid_entry_price" in assessment1.reasons
    
    # NaN ATR
    assessment2 = service.assess(signal, Decimal("1000"), Decimal("NaN"), Decimal("10000"))
    assert assessment2.eligible_for_paper_trading is False
    assert "invalid_atr" in assessment2.reasons


def test_risk_manager_rejects_negative_targets(risk_settings: RiskSettings) -> None:
    service = RiskManagerService(risk_settings)
    signal = _make_signal(SignalDirection.SHORT, "100")
    
    # entry 10, ATR 6 -> stop dist 9. take profit = 10 - 18 = -8
    # note: atr fraction 6/10 = 0.6, so we must increase max atr fraction temporarily to test target
    settings = RiskSettings(maximum_atr_fraction=Decimal("1.0"))
    service = RiskManagerService(settings)
    
    assessment = service.assess(signal, Decimal("10"), Decimal("6"), Decimal("1000"))
    assert assessment.eligible_for_paper_trading is False
    assert "invalid_price_levels" in assessment.reasons
