"""
MarketPilot Engines � Risk Engine.

Evaluates StrategyEvaluations against risk constraints.
Outputs RiskDecision which dictates position sizing and trade viability.
"""

from __future__ import annotations

import time
from decimal import Decimal

from marketpilot.config.settings import RiskSettings
from marketpilot.models.risk import RiskDecision
from marketpilot.models.strategy import StrategyEvaluation
from marketpilot.models.core import EngineMetadata

class RiskEngine:
    """Evaluates strategy proposals against risk parameters to produce a RiskDecision."""

    def __init__(self, settings: RiskSettings):
        self._settings = settings

    def evaluate(
        self, 
        eval_result: StrategyEvaluation, 
        market_health: Decimal,
        account_equity: Decimal,
        decision_id: str
    ) -> tuple[RiskDecision, EngineMetadata]:
        """Produce a RiskDecision for the given StrategyEvaluation."""
        start_time = time.time()
        
        def meta() -> EngineMetadata:
            return EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000, decision_id=decision_id)
        
        # Rule: Market Health < 40 -> NO NEW POSITION
        if market_health < Decimal("40"):
            return RiskDecision(
                approved=False,
                reason=f"Rejected: Market Health ({market_health:.2f}) is below minimum threshold (40).",
                position_size=Decimal("0"),
                risk_amount=Decimal("0"),
                sl=Decimal("0"),
                tp=Decimal("0"),
                rr=Decimal("0")
            ), meta()

        # Rule: Minimum RR
        if eval_result.expected_rr < self._settings.minimum_reward_risk:
            return RiskDecision(
                approved=False,
                reason=f"Rejected: Expected RR ({eval_result.expected_rr:.2f}) below minimum ({self._settings.minimum_reward_risk:.2f}).",
                position_size=Decimal("0"),
                risk_amount=Decimal("0"),
                sl=eval_result.stop_loss,
                tp=eval_result.take_profit,
                rr=eval_result.expected_rr
            ), meta()

        # Calculate Risk Amount (Quote Coin)
        risk_amount = account_equity * self._settings.risk_per_trade_fraction
        
        # Calculate Position Size (Base Coin)
        # Risk per unit = abs(Entry - SL)
        risk_per_unit = (eval_result.entry_price - eval_result.stop_loss).copy_abs()
        
        if risk_per_unit == Decimal("0"):
            return RiskDecision(
                approved=False,
                reason="Rejected: Stop loss distance is zero, infinite risk.",
                position_size=Decimal("0"),
                risk_amount=Decimal("0"),
                sl=eval_result.stop_loss,
                tp=eval_result.take_profit,
                rr=eval_result.expected_rr
            ), meta()
            
        # Volatility check
        volatility = risk_per_unit / eval_result.entry_price
        if volatility > self._settings.maximum_atr_fraction:
            return RiskDecision(
                approved=False,
                reason=f"Rejected: Volatility/SL Distance ({volatility*100:.2f}%) exceeds maximum allowed ({self._settings.maximum_atr_fraction*100:.2f}%).",
                position_size=Decimal("0"),
                risk_amount=Decimal("0"),
                sl=eval_result.stop_loss,
                tp=eval_result.take_profit,
                rr=eval_result.expected_rr
            ), meta()

        position_size = risk_amount / risk_per_unit

        return RiskDecision(
            approved=True,
            reason="Approved: Passed all risk checks.",
            position_size=position_size.quantize(Decimal("0.0001")), # Simplistic rounding
            risk_amount=risk_amount.quantize(Decimal("0.01")),
            sl=eval_result.stop_loss,
            tp=eval_result.take_profit,
            rr=eval_result.expected_rr
        ), meta()
