"""
MarketPilot Research - Feature Store.

Extracts feature vectors from TradeExecutionRecords.
"""

from typing import Any
import pandas as pd
from marketpilot.models.journal import TradeExecutionRecord

class FeatureStore:
    """Manages the mapping of decision_id -> feature vector -> trade outcome."""
    
    @staticmethod
    def extract_features(record: TradeExecutionRecord) -> dict[str, Any]:
        """Extracts numerical features from a TradeExecutionRecord for ML."""
        # This acts as a bridge between rule-based data and institutional research.
        plan = record.trade_plan
        return {
            "decision_id": record.decision_id,
            "symbol": plan.symbol,
            "strategy": plan.strategy,
            "direction": plan.direction.value,
            "market_regime": plan.market_regime.value if plan.market_regime else "UNKNOWN",
            "confidence": float(plan.confidence),
            "expected_rr": float(plan.expected_rr),
            "market_quality": float(plan.market_quality),
            "risk_pct": float(plan.risk),
            
            # Simulated outcome features (In real life, this comes from closed positions)
            # We assume closed profit here for demonstration.
            "realized_pnl_r": 2.0 if record.execution_status.value == "SUCCESS" else -1.0,
            "holding_time_mins": 120.0,
        }
        
    @staticmethod
    def records_to_dataframe(records: list[TradeExecutionRecord]) -> pd.DataFrame:
        """Converts raw records into an ML-ready feature DataFrame."""
        features = [FeatureStore.extract_features(r) for r in records]
        return pd.DataFrame(features)
