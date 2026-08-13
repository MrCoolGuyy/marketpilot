"""
MarketPilot Research - Report Models.

Data structures representing the output of the Performance & Research Engine.
"""

from typing import Dict, Any, Optional
from decimal import Decimal
from pydantic import BaseModel, Field

class PerformanceReport(BaseModel, frozen=True):
    """Core KPIs across all trades."""
    total_trades: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    system_quality_number: float
    
    max_drawdown_pct: float
    current_drawdown_pct: float
    
    avg_holding_time_mins: float
    mae_avg_pct: float
    mfe_avg_pct: float
    
    monte_carlo_prob_ruin: float
    monte_carlo_expected_recovery_days: float

class StrategyReport(BaseModel, frozen=True):
    """KPI breakdown for a specific strategy."""
    strategy_name: str
    total_trades: int
    win_rate: float
    expectancy_r: float
    profit_factor: float
    sharpe_ratio: float
    recommendation: str = Field(..., description="'KEEP', 'TUNE', or 'DISABLE'")
    reason: str

class RegimeReport(BaseModel, frozen=True):
    """Performance breakdown across market regimes."""
    regime_name: str
    total_trades: int
    expectancy_r: float
    win_rate: float

class FeatureReport(BaseModel, frozen=True):
    """Analysis of how specific features impact performance."""
    feature_name: str
    condition: str
    total_trades: int
    win_rate: float
    profit_factor: float
    importance_score: float = Field(0.0, description="Permutation importance or mutual information score")

class ComprehensiveResearchReport(BaseModel, frozen=True):
    """The master report containing all analysis."""
    overall_performance: PerformanceReport
    strategies: list[StrategyReport]
    regimes: list[RegimeReport]
    features: list[FeatureReport]
