"""Tests for Risk Engine."""

from decimal import Decimal
import pytest

from marketpilot.config.settings import RiskSettings
from marketpilot.engines.risk_engine import RiskEngine
from marketpilot.models.strategy import StrategyEvaluation, SignalDirection

def test_risk_engine_market_health_rejection() -> None:
    settings = RiskSettings()
    engine = RiskEngine(settings)
    
    eval_result = StrategyEvaluation(
        expected_win_rate=Decimal("50"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("96"), # Distance 4 (4%)
        take_profit=Decimal("108"), # RR = 8/4 = 2.0
        expected_rr=Decimal("2.0")
    )
    
    # Rejects if < 40
    decision, meta = engine.evaluate(eval_result, market_health=Decimal("39.99"), account_equity=Decimal("10000"), decision_id="test-1")
    assert not decision.approved
    assert "Market Health" in decision.reason
    assert meta.decision_id == "test-1"
    
    # Approves if >= 40
    decision2, meta2 = engine.evaluate(eval_result, market_health=Decimal("40.00"), account_equity=Decimal("10000"), decision_id="test-2")
    assert decision2.approved
    
def test_risk_engine_rr_rejection() -> None:
    settings = RiskSettings(minimum_reward_risk=Decimal("2.0"))
    engine = RiskEngine(settings)
    
    eval_result = StrategyEvaluation(
        expected_win_rate=Decimal("50"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("115"), # RR = 15/10 = 1.5
        expected_rr=Decimal("1.5")
    )
    
    decision, meta = engine.evaluate(eval_result, market_health=Decimal("50"), account_equity=Decimal("10000"), decision_id="test-1")
    assert not decision.approved
    assert "Expected RR" in decision.reason

def test_risk_engine_position_sizing() -> None:
    settings = RiskSettings(risk_per_trade_fraction=Decimal("0.02")) # 2% risk
    engine = RiskEngine(settings)
    
    eval_result = StrategyEvaluation(
        expected_win_rate=Decimal("50"),
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"), # Risk = 5 per unit
        take_profit=Decimal("110"), # RR = 15/5 = 3
        expected_rr=Decimal("3.0")
    )
    
    decision, meta = engine.evaluate(eval_result, market_health=Decimal("50"), account_equity=Decimal("10000"), decision_id="test-1")
    assert decision.approved
    
    # 2% of 10,000 = 200 risk amount
    assert decision.risk_amount == Decimal("200.00")
    
    # 200 / 5 = 40 units
    assert decision.position_size == Decimal("40.0000")
