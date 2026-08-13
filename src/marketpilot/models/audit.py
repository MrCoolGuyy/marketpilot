"""
MarketPilot Models - Audit domain models.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from marketpilot.models.scanner import InstrumentSnapshot
from marketpilot.models.regime import MarketRegime
from marketpilot.models.strategy import StrategyResult
from marketpilot.models.risk import RiskDecision
from marketpilot.models.trade import TradePlan

class AuditRecord(BaseModel):
    """The complete flight recorder snapshot of a single trading decision."""
    
    decision_id: str = Field(..., description="Unique UUID for this pipeline execution")
    timestamp: float = Field(..., description="Unix timestamp of when the decision was finalized")
    config_hash: str = Field(..., description="Hash of the configuration used for this decision")
    
    # 1. Scanner Context
    market_snapshot: InstrumentSnapshot = Field(..., description="The market state at the time")
    
    # 2. Indicator Context (Feature Vector)
    feature_vector: dict[str, str] = Field(..., description="Raw indicator values (e.g. EMA, RSI) for ML datasets")
    
    # 3. Regime Context
    regime_snapshot: MarketRegime = Field(..., description="The classified market regime")
    
    # 4. Strategy Context
    strategy_results: list[StrategyResult] = Field(..., description="The immutable outcomes from all evaluated strategies")
    
    # 5. Risk Context (Optional if no strategy proposed a trade)
    risk_result: Optional[RiskDecision] = Field(default=None, description="The outcome from the risk engine")
    
    # 6. Trade Plan (Optional if risk rejected or no trade proposed)
    trade_plan: Optional[TradePlan] = Field(default=None, description="The original proposed trade plan")
    
    # 7. Validation Context
    validation_passed: Optional[bool] = Field(default=None, description="Whether the plan passed exchange validation")
    validation_reason: Optional[str] = Field(default=None, description="Reason for validation success/failure")
    quantized_plan: Optional[TradePlan] = Field(default=None, description="The final TradePlan after tick/step quantization")
    
    # 8. Execution Context (Will be updated by Phase 4 later if executed)
    execution_submitted: bool = Field(default=False, description="Whether an order was actually sent to the exchange")
    
    # Observability
    total_processing_time_ms: float = Field(default=0.0, description="End-to-end pipeline processing time")
