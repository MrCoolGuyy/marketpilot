"""
MarketPilot Research - Performance Metrics.

Calculates institutional KPIs (Sharpe, SQN, Expectancy, Drawdown) from trades.
"""

import numpy as np
import pandas as pd

class PerformanceMetrics:
    @staticmethod
    def calculate_kpis(pnl_r_series: pd.Series) -> dict[str, float]:
        """Calculates core and risk-adjusted KPIs given a series of PnL in R-multiples."""
        if pnl_r_series.empty:
            return _empty_kpis()
            
        total_trades = len(pnl_r_series)
        wins = pnl_r_series[pnl_r_series > 0]
        losses = pnl_r_series[pnl_r_series <= 0]
        
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
        expectancy_r = pnl_r_series.mean()
        
        gross_profit = wins.sum() if not wins.empty else 0.0
        gross_loss = abs(losses.sum()) if not losses.empty else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
        
        # Risk Adjusted Returns
        std_dev = pnl_r_series.std()
        sharpe = (expectancy_r / std_dev) if std_dev and std_dev > 0 else 0.0
        
        downside_returns = pnl_r_series[pnl_r_series < 0]
        downside_dev = downside_returns.std()
        sortino = (expectancy_r / downside_dev) if downside_dev and downside_dev > 0 else 0.0
        
        # System Quality Number (SQN) = sqrt(N) * (Expectancy / StdDev)
        sqn = np.sqrt(total_trades) * sharpe if std_dev else 0.0
        
        # Drawdown
        cumulative = pnl_r_series.cumsum()
        running_max = cumulative.cummax()
        drawdowns = running_max - cumulative
        max_drawdown = drawdowns.max()
        current_drawdown = drawdowns.iloc[-1] if not drawdowns.empty else 0.0
        
        # Calmar Ratio
        calmar = (expectancy_r * total_trades) / max_drawdown if max_drawdown > 0 else 0.0
        
        return {
            "total_trades": total_trades,
            "win_rate": float(win_rate),
            "expectancy_r": float(expectancy_r),
            "profit_factor": float(profit_factor),
            "sharpe_ratio": float(sharpe),
            "sortino_ratio": float(sortino),
            "calmar_ratio": float(calmar),
            "system_quality_number": float(sqn),
            "max_drawdown_pct": float(max_drawdown), # Assuming R correlates to % risk
            "current_drawdown_pct": float(current_drawdown)
        }

def _empty_kpis() -> dict[str, float]:
    return {
        "total_trades": 0, "win_rate": 0.0, "expectancy_r": 0.0,
        "profit_factor": 0.0, "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
        "calmar_ratio": 0.0, "system_quality_number": 0.0,
        "max_drawdown_pct": 0.0, "current_drawdown_pct": 0.0
    }
