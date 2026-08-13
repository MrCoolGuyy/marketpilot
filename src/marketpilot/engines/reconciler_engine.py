"""
MarketPilot Engines - Execution Reconciler.

Compares ExecutionResult against the original TradePlan.
Calculates slippage, fees, and emits AuditWarnings for discrepancies.
Resolves UNKNOWN execution statuses.
"""

from __future__ import annotations

from decimal import Decimal

from marketpilot.models.trade import TradePlan
from marketpilot.models.execution import ExecutionResult, ExecutionStatus
from marketpilot.models.reconciliation import ReconciliationReport

class ReconcilerEngine:
    """Reconciles executed orders against their original trade plan."""

    def reconcile(self, plan: TradePlan, result: ExecutionResult, actual_fee: Decimal = Decimal("0"), is_maker: bool = False) -> ReconciliationReport:
        warnings = []
        
        # 1. Resolve UNKNOWN Status
        if result.status == ExecutionStatus.UNKNOWN:
            # Reconciler forces MANUAL_REVIEW for UNKNOWNs
            warnings.append("Execution status was UNKNOWN. Manual review required to prevent double-spend or desync.")
            
        qty_mismatch = plan.qty != result.executed_qty
        if qty_mismatch:
            warnings.append(f"Quantity mismatch: Expected {plan.qty}, Executed {result.executed_qty}")
            
        # 2. Calculate Slippage BPS
        # BPS = (Actual - Expected) / Expected * 10000
        # If BUY/LONG: Actual > Expected is positive slippage (bad)
        # If SELL/SHORT: Expected > Actual is positive slippage (bad)
        slippage_bps = Decimal("0")
        if plan.entry > Decimal("0") and result.executed_price > Decimal("0"):
            diff = result.executed_price - plan.entry
            if plan.direction.value == "SHORT":
                diff = plan.entry - result.executed_price
                
            slippage_bps = (diff / plan.entry) * Decimal("10000")
            
        if slippage_bps > Decimal("10"): # >10 bps slippage warning
            warnings.append(f"High slippage detected: {slippage_bps:.2f} bps")
            
        # 3. Fees and Spread
        expected_fee_rate = Decimal("0.0002") if is_maker else Decimal("0.00055") # Bybit VIP0 defaults
        expected_fee = (result.executed_qty * result.executed_price) * expected_fee_rate
        
        fee_diff = (actual_fee - expected_fee).copy_abs()
        if fee_diff > (expected_fee * Decimal("0.1")):
            warnings.append(f"Fee mismatch: Expected {expected_fee:.4f}, Actual {actual_fee:.4f}")
            
        return ReconciliationReport(
            decision_id=plan.decision_id,
            expected_entry=plan.entry,
            executed_entry=result.executed_price,
            slippage_bps=slippage_bps.quantize(Decimal("0.01")),
            expected_qty=plan.qty,
            executed_qty=result.executed_qty,
            qty_mismatch=qty_mismatch,
            expected_fee=expected_fee.quantize(Decimal("0.0001")),
            actual_fee=actual_fee.quantize(Decimal("0.0001")),
            is_maker=is_maker,
            realized_spread=Decimal("0"), # Needs bid/ask data at execution time, omit for now
            warnings=warnings
        )
