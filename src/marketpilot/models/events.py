"""
MarketPilot Models - Pipeline Events.

Immutable events that drive the Trading Pipeline.
"""

from __future__ import annotations

from marketpilot.core.event_bus import PipelineEvent
from marketpilot.models.mission_control import PipelineContext
from marketpilot.models.scanner import ScannerResult, InstrumentSnapshot
from marketpilot.models.indicators import IndicatorSeries
from marketpilot.models.regime import MarketRegime
from marketpilot.models.strategy import StrategyResult
from marketpilot.models.trade import TradePlan
from marketpilot.models.execution import ExecutionResult
from marketpilot.models.reconciliation import ReconciliationReport

class ContextualEvent(PipelineEvent):
    """Base for events that carry a PipelineContext."""
    ctx: PipelineContext

class CycleStartedEvent(ContextualEvent):
    pass

class ScannerFinishedEvent(ContextualEvent):
    scanner_result: ScannerResult

class IndicatorsFinishedEvent(ContextualEvent):
    scanner_result: ScannerResult
    indicators: dict[str, IndicatorSeries]

class RegimeFinishedEvent(ContextualEvent):
    scanner_result: ScannerResult
    indicators: dict[str, IndicatorSeries]
    regimes: dict[str, MarketRegime]

class StrategyFinishedEvent(ContextualEvent):
    scanner_result: ScannerResult
    regimes: dict[str, MarketRegime]
    strategy_results: list[StrategyResult]

class RiskFinishedEvent(ContextualEvent):
    trade_plan: TradePlan

class ExecutionCompletedEvent(ContextualEvent):
    trade_plan: TradePlan
    execution_result: ExecutionResult

class ReconciliationCompletedEvent(ContextualEvent):
    trade_plan: TradePlan
    execution_result: ExecutionResult
    report: ReconciliationReport
    
class JournalCompletedEvent(ContextualEvent):
    pass

class CycleFinishedEvent(ContextualEvent):
    pass
