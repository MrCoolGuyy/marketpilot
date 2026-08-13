"""
MarketPilot Research - Monte Carlo Simulation.

Evaluates system robustness via Trade Shuffle and Bootstrap Sampling.
"""

import numpy as np
import pandas as pd

class MonteCarloSimulator:
    def __init__(self, iterations: int = 1000):
        self.iterations = iterations
        
    def simulate_ruin_probability(self, pnl_r_series: pd.Series, ruin_threshold_r: float = 20.0) -> float:
        """
        Calculates the Probability of Ruin (hitting drawdown threshold) using Bootstrap Sampling.
        This provides a more robust estimate than simple historical drawdown.
        """
        if pnl_r_series.empty or len(pnl_r_series) < 10:
            return 1.0 # Not enough data, assume ruin
            
        ruin_count = 0
        n_trades = len(pnl_r_series)
        
        for _ in range(self.iterations):
            # Bootstrap sampling with replacement
            sample = pnl_r_series.sample(n=n_trades, replace=True).values
            cumulative = np.cumsum(sample)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = running_max - cumulative
            
            if np.max(drawdowns) >= ruin_threshold_r:
                ruin_count += 1
                
        return ruin_count / self.iterations
        
    def expected_recovery_days(self, pnl_r_series: pd.Series, avg_trades_per_day: float = 5.0) -> float:
        """Estimates expected recovery time from Max Drawdown via Trade Shuffle."""
        if pnl_r_series.empty or len(pnl_r_series) < 10:
            return 999.0
            
        recovery_trades_list = []
        n_trades = len(pnl_r_series)
        
        for _ in range(self.iterations):
            # Shuffle without replacement
            sample = pnl_r_series.sample(frac=1.0, replace=False).values
            cumulative = np.cumsum(sample)
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = running_max - cumulative
            
            # Find max DD index
            max_dd_idx = np.argmax(drawdowns)
            
            # Find when cumulative equity breaks above the previous peak
            peak_equity = running_max[max_dd_idx]
            recovery_idx = -1
            
            for i in range(max_dd_idx + 1, n_trades):
                if cumulative[i] > peak_equity:
                    recovery_idx = i
                    break
                    
            if recovery_idx != -1:
                recovery_trades_list.append(recovery_idx - max_dd_idx)
                
        if not recovery_trades_list:
            return 999.0 # Never recovered in simulations
            
        avg_recovery_trades = np.mean(recovery_trades_list)
        return float(avg_recovery_trades / avg_trades_per_day)
