"""
MarketPilot Optimization — Parameter Search Service.
"""

from __future__ import annotations

import itertools
from decimal import Decimal
from typing import Sequence

from marketpilot.backtest.engine import BacktestEngine
from marketpilot.config.settings import OptimizationSettings, StrategySettings
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.market import Kline
from marketpilot.models.optimization import CandidateResult, OptimizationCandidate, OptimizationResult
from marketpilot.risk.service import RiskManagerService
from marketpilot.strategy.service import StrategyService


class OptimizationService:
    """Historical parameter search engine."""

    def __init__(
        self,
        settings: OptimizationSettings,
        indicator_service: IndicatorService,
        risk_service: RiskManagerService,
        baseline_strategy_settings: StrategySettings,
        backtest_settings_factory: type,
        backtest_settings_kwargs: dict,
    ) -> None:
        self._settings = settings
        self._indicator_service = indicator_service
        self._risk_service = risk_service
        self._baseline_strategy_settings = baseline_strategy_settings
        self._backtest_settings_factory = backtest_settings_factory
        self._backtest_settings_kwargs = backtest_settings_kwargs

    def optimize(self, klines: Sequence[Kline]) -> OptimizationResult:
        """Run parameter optimization over the given klines."""
        if not klines:
            raise ValueError("No klines provided for optimization")

        # 1. Split chronologically
        total_klines = len(klines)
        split_idx = int(total_klines * float(self._settings.train_fraction))
        
        # Validation requires enough candles for warmup and evaluation.
        # Arbitrarily, require at least 50 candles in each split to ensure EMA/RSI can warm up.
        if split_idx < 50 or (total_klines - split_idx) < 50:
            raise ValueError(f"Insufficient klines for split. Train: {split_idx}, Val: {total_klines - split_idx}. Minimum 50 required for each.")

        train_klines = klines[:split_idx]
        split_time = klines[split_idx].open_time

        # 2. Generate and deduplicate candidates
        candidates_dict: dict[tuple, OptimizationCandidate] = {}
        
        # Baseline candidate
        baseline_key = (
            self._baseline_strategy_settings.rsi_long_min,
            self._baseline_strategy_settings.rsi_long_max,
            self._baseline_strategy_settings.rsi_short_min,
            self._baseline_strategy_settings.rsi_short_max,
        )
        candidates_dict[baseline_key] = OptimizationCandidate(
            label="baseline",
            strategy_settings=self._baseline_strategy_settings
        )

        # Grid candidates
        grid = itertools.product(
            self._settings.grid_rsi_long_min,
            self._settings.grid_rsi_long_max,
            self._settings.grid_rsi_short_min,
            self._settings.grid_rsi_short_max,
        )
        
        for i, (l_min, l_max, s_min, s_max) in enumerate(grid):
            # Check validity
            if l_min > l_max or s_min > s_max or s_max >= l_min:
                continue
                
            key = (l_min, l_max, s_min, s_max)
            if key not in candidates_dict:
                try:
                    strat_settings = StrategySettings(
                        rsi_long_min=l_min,
                        rsi_long_max=l_max,
                        rsi_short_min=s_min,
                        rsi_short_max=s_max
                    )
                    candidates_dict[key] = OptimizationCandidate(
                        label=f"grid_{i}",
                        strategy_settings=strat_settings
                    )
                except ValueError:
                    # Ignore invalid parameter combinations that fail validation
                    continue

        candidates = list(candidates_dict.values())
        if len(candidates) > self._settings.maximum_candidates:
            raise ValueError(f"Generated {len(candidates)} candidates, which exceeds the maximum of {self._settings.maximum_candidates}")

        # 3. Evaluate candidates
        results: list[CandidateResult] = []
        
        # We need a backtest settings instance
        backtest_settings = self._backtest_settings_factory(**self._backtest_settings_kwargs)

        for candidate in candidates:
            # Train phase
            strategy_service = StrategyService(candidate.strategy_settings)
            engine = BacktestEngine(
                settings=backtest_settings,
                indicator_service=self._indicator_service,
                strategy_service=strategy_service,
                risk_service=self._risk_service
            )
            
            # Run on training split
            train_result = engine.run(train_klines)
            
            # Eligibility
            if train_result.metrics.trade_count < self._settings.minimum_train_trades:
                results.append(CandidateResult(
                    candidate=candidate,
                    train_metrics=train_result.metrics,
                    val_metrics=None,
                    train_objective=None,
                    is_eligible=False,
                    rejection_reason=f"Only {train_result.metrics.trade_count} trades (minimum {self._settings.minimum_train_trades})"
                ))
                continue
                
            # Train objective
            train_obj = train_result.metrics.total_return_fraction - train_result.metrics.max_drawdown_fraction
            
            # Validation phase
            # Pass ALL klines, but start trading precisely at split_idx
            val_result = engine.run(klines, trading_start_index=split_idx)
            
            results.append(CandidateResult(
                candidate=candidate,
                train_metrics=train_result.metrics,
                val_metrics=val_result.metrics,
                train_objective=train_obj,
                is_eligible=True,
                rejection_reason=None
            ))

        # 4. Rank candidates
        # Deterministic sorting: train_obj (desc), train drawdown (asc), label (asc)
        eligible_results = [r for r in results if r.is_eligible and r.train_objective is not None and r.train_metrics is not None]
        
        eligible_results.sort(
            key=lambda r: (
                -float(r.train_objective), # type: ignore
                float(r.train_metrics.max_drawdown_fraction), # type: ignore
                r.candidate.label
            )
        )
        
        best = eligible_results[0] if eligible_results else None

        return OptimizationResult(
            symbol=klines[0].symbol,
            interval=klines[0].interval,
            split_time=split_time,
            candidates=tuple(results),
            best_candidate=best
        )
