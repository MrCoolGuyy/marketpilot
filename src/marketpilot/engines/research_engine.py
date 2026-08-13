"""
MarketPilot Research - Performance & Research Engine.

Orchestrates all analytics modules to produce the ComprehensiveResearchReport.
"""

import time
import pandas as pd
from typing import Optional

from marketpilot.models.journal import TradeExecutionRecord
from marketpilot.models.research.reports import (
    ComprehensiveResearchReport, PerformanceReport,
    StrategyReport, RegimeReport, FeatureReport
)
from marketpilot.models.research.manifest import ResearchManifest
from marketpilot.research.feature_store import FeatureStore
from marketpilot.research.dataset_builder import DatasetBuilder
from marketpilot.research.metrics import PerformanceMetrics
from marketpilot.research.monte_carlo import MonteCarloSimulator
from marketpilot.research.calibration import ConfidenceCalibrator
from marketpilot.research.feature_importance import FeatureAnalyzer
from marketpilot.research.governance import StrategyGovernance


class ResearchEngine:
    def __init__(self, version: str = "1.0.0", config_hash: str = "unknown"):
        self.version = version
        self.config_hash = config_hash
        self.dataset_builder = DatasetBuilder()
        self.monte_carlo = MonteCarloSimulator(iterations=1000)

    def generate_report(self, records: list[TradeExecutionRecord]) -> tuple[ComprehensiveResearchReport, ResearchManifest]:
        """Main entry point for the Research Platform."""
        if not records:
            raise ValueError("No trade records provided for research.")

        # 1. Feature Extraction & Dataset Generation
        df = FeatureStore.records_to_dataframe(records)
        
        # Save to Parquet
        self.dataset_builder.save_features(df)
        self.dataset_builder.save_trades(df)  # In a real app, separate raw trades vs features
        
        # 2. Overall Performance
        pnl_series = df["realized_pnl_r"]
        kpis = PerformanceMetrics.calculate_kpis(pnl_series)
        
        prob_ruin = self.monte_carlo.simulate_ruin_probability(pnl_series)
        exp_recovery = self.monte_carlo.expected_recovery_days(pnl_series)
        
        overall_perf = PerformanceReport(
            **kpis,
            monte_carlo_prob_ruin=prob_ruin,
            monte_carlo_expected_recovery_days=exp_recovery,
            avg_holding_time_mins=float(df["holding_time_mins"].mean()),
            mae_avg_pct=0.0, # Placeholder until tick data integration
            mfe_avg_pct=0.0  # Placeholder until tick data integration
        )

        # 3. Strategy Analysis
        strategies = []
        for strat in df["strategy"].unique():
            strat_df = df[df["strategy"] == strat]
            strat_kpis = PerformanceMetrics.calculate_kpis(strat_df["realized_pnl_r"])
            
            rec, reason = StrategyGovernance.evaluate_strategy(
                profit_factor=strat_kpis["profit_factor"],
                expectancy_r=strat_kpis["expectancy_r"],
                trade_count=strat_kpis["total_trades"],
                max_drawdown_pct=strat_kpis["max_drawdown_pct"]
            )
            
            strategies.append(StrategyReport(
                strategy_name=str(strat),
                total_trades=strat_kpis["total_trades"],
                win_rate=strat_kpis["win_rate"],
                expectancy_r=strat_kpis["expectancy_r"],
                profit_factor=strat_kpis["profit_factor"],
                sharpe_ratio=strat_kpis["sharpe_ratio"],
                recommendation=rec,
                reason=reason
            ))

        # 4. Regime Analysis
        regimes = []
        for regime in df["market_regime"].unique():
            reg_df = df[df["market_regime"] == regime]
            reg_kpis = PerformanceMetrics.calculate_kpis(reg_df["realized_pnl_r"])
            regimes.append(RegimeReport(
                regime_name=str(regime),
                total_trades=reg_kpis["total_trades"],
                expectancy_r=reg_kpis["expectancy_r"],
                win_rate=reg_kpis["win_rate"]
            ))

        # 5. Feature Importance
        # Convert outcomes to binary for Mutual Information
        outcomes = (df["realized_pnl_r"] > 0).astype(int)
        mi_scores = FeatureAnalyzer.calculate_mutual_information(df, outcomes)
        
        features = []
        for feat, score in mi_scores.items():
            if score > 0.0:  # Only report features with some predictive power
                features.append(FeatureReport(
                    feature_name=feat,
                    condition="N/A", # Needs rule extraction logic
                    total_trades=len(df),
                    win_rate=kpis["win_rate"],
                    profit_factor=kpis["profit_factor"],
                    importance_score=score
                ))

        # 6. Construct Final Artifacts
        report = ComprehensiveResearchReport(
            overall_performance=overall_perf,
            strategies=strategies,
            regimes=regimes,
            features=features
        )
        
        manifest = ResearchManifest(
            analytics_version=self.version,
            dataset_hash="hash_" + str(hash(df.to_json())),
            config_hash=self.config_hash,
            python_version="3.14",
            created_time=time.time(),
            trade_count=len(df),
            feature_count=len(df.columns)
        )
        
        return report, manifest
