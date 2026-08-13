"""
MarketPilot Research - Strategy Governance.

Provides automated recommendations (KEEP, TUNE, DISABLE) based on empirical KPIs.
"""

from typing import Literal

Recommendation = Literal["KEEP", "TUNE", "DISABLE"]

class StrategyGovernance:
    @staticmethod
    def evaluate_strategy(
        profit_factor: float,
        expectancy_r: float,
        trade_count: int,
        max_drawdown_pct: float
    ) -> tuple[Recommendation, str]:
        """
        Determines if a strategy should be retired or tuned.
        Never mutates the strategy automatically. Read-only recommendation.
        """
        if trade_count < 30:
            return "KEEP", f"Insufficient sample size ({trade_count} trades). Minimum 30 required."
            
        if profit_factor < 1.0 and trade_count > 150 and expectancy_r < 0:
            return "DISABLE", f"Sustained negative edge. PF={profit_factor:.2f}, Trades={trade_count}"
            
        if profit_factor < 1.2 or expectancy_r < 0.1:
            return "TUNE", f"Marginal edge detected. PF={profit_factor:.2f}, Expectancy={expectancy_r:.2f}R"
            
        if max_drawdown_pct > 30.0:
            return "TUNE", f"Excessive drawdown ({max_drawdown_pct:.1f}%). Requires risk parameter tuning."
            
        return "KEEP", "Strategy demonstrates robust statistical edge."
