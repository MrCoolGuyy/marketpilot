"""
MarketPilot Models — Optimization domain models.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from marketpilot.config.settings import StrategySettings
from marketpilot.core.enums import Interval
from marketpilot.models.backtest import BacktestMetrics


class OptimizationCandidate(BaseModel, frozen=True):
    """A single strategy parameter combination."""

    label: str
    strategy_settings: StrategySettings


class CandidateResult(BaseModel, frozen=True):
    """The backtest metrics for a candidate on train and validation."""

    candidate: OptimizationCandidate
    train_metrics: BacktestMetrics | None
    val_metrics: BacktestMetrics | None
    train_objective: Decimal | None
    is_eligible: bool
    rejection_reason: str | None


class OptimizationResult(BaseModel, frozen=True):
    """The result of an optimization run."""

    symbol: str
    interval: Interval
    split_time: datetime
    candidates: tuple[CandidateResult, ...]
    best_candidate: CandidateResult | None
