"""
MarketPilot Models - Execution Policy models.
"""

from __future__ import annotations

from typing import Literal
from decimal import Decimal
from pydantic import BaseModel, Field


class ExecutionValidationPolicy(BaseModel, frozen=True):
    version: str = "1.0.0"
    max_quantity_deviation_bps: int = Field(
        default=200, description="Max allowed risk deviation from quantization"
    )
    allow_quantity_increase: Literal[False] = False


class ExecutionProtectionPolicy(BaseModel, frozen=True):
    version: str = "1.0.0"
    sl_trigger_by: Literal["LastPrice", "IndexPrice", "MarkPrice"] = "LastPrice"
    tpsl_mode: Literal["Full", "Partial"] = "Full"
    sl_order_type: Literal["Market", "Limit"] = "Market"
    require_attached_stop_for_demo: Literal[True] = True


class ExecutionReconciliationPolicy(BaseModel, frozen=True):
    version: str = "1.0.0"
    normal_poll_cadence_seconds: int = 15
    unknown_poll_cadence_seconds: int = 5
    max_staleness_seconds: int = 60
    history_coverage_required: Literal[True] = True


class PaperExecutionPolicy(BaseModel, frozen=True):
    version: str = "1.0.0"
    require_fresh_quote: Literal[True] = True
    fee_rate_bps: Decimal = Decimal("5.5")
    slippage_bps: Decimal = Decimal("2.0")
    fill_behavior: Literal["DETERMINISTIC_FULL", "DETERMINISTIC_PARTIAL"] = "DETERMINISTIC_FULL"
