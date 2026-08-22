"""
MarketPilot Engines - Order Validator.

Ensures that an ExecutionIntent conforms to the exchange's strict instrument rules
such as tick size, qty step, min/max limits, and validates quantized risk.
"""

from __future__ import annotations

import time
import hashlib
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from typing import Optional

from marketpilot.models.execution import ExecutionIntent, ValidatedOrderSpec
from marketpilot.models.execution_policy import ExecutionValidationPolicy
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.models.core import EngineMetadata


class OrderValidationRejection(Exception):
    """Raised when an intent cannot be validly quantized or violates policy."""

    pass


class OrderValidator:
    """Validates and quantizes ExecutionIntents into ValidatedOrderSpecs."""

    def __init__(self, policy: ExecutionValidationPolicy):
        self.policy = policy

    def _quantize_qty(self, qty: Decimal, qty_step: Decimal) -> Decimal:
        """Always floor quantity to step, never increase admitted quantity."""
        if qty_step == Decimal("0"):
            return qty
        steps = qty // qty_step
        return steps * qty_step

    def _quantize_price(self, price: Decimal, tick_size: Decimal, rounding: str) -> Decimal:
        """Snap a price to tick_size using strict ROUND_FLOOR or ROUND_CEILING."""
        if tick_size == Decimal("0"):
            return price
        ticks = (price / tick_size).quantize(Decimal("1"), rounding=rounding)
        return ticks * tick_size

    def validate_intent(
        self,
        intent: ExecutionIntent,
        instrument: InstrumentInfo,
    ) -> ValidatedOrderSpec:
        """
        Validates the intent and side-aware quantizes prices/quantities.
        Returns a ValidatedOrderSpec or raises OrderValidationRejection.
        """
        if instrument.status.lower() != "trading":
            raise OrderValidationRejection(f"Instrument status is {instrument.status}")

        qty_step = Decimal(instrument.qty_step)
        tick_size = Decimal(instrument.tick_size)
        min_qty = Decimal(instrument.min_order_qty)
        max_qty = Decimal(instrument.max_order_qty) if instrument.max_order_qty else Decimal("Inf")

        # 1. Quantity Quantization
        q_qty = self._quantize_qty(intent.original_qty, qty_step)

        if q_qty < min_qty:
            raise OrderValidationRejection(f"Quantized qty {q_qty} below min {min_qty}")
        if q_qty > max_qty:
            raise OrderValidationRejection(f"Quantized qty {q_qty} above max {max_qty}")

        if not self.policy.allow_quantity_increase and q_qty > intent.original_qty:
            raise OrderValidationRejection("Policy forbids quantity increase")

        # 2. Side-aware Price Quantization
        if intent.side == "LONG":
            q_entry = self._quantize_price(intent.executable_entry, tick_size, ROUND_FLOOR)
            q_sl = self._quantize_price(
                intent.effective_stop, tick_size, ROUND_CEILING
            )  # towards entry
            q_tp = (
                self._quantize_price(intent.take_profit, tick_size, ROUND_FLOOR)
                if intent.take_profit
                else None
            )
        else:  # SHORT
            q_entry = self._quantize_price(intent.executable_entry, tick_size, ROUND_CEILING)
            q_sl = self._quantize_price(
                intent.effective_stop, tick_size, ROUND_FLOOR
            )  # towards entry
            q_tp = (
                self._quantize_price(intent.take_profit, tick_size, ROUND_CEILING)
                if intent.take_profit
                else None
            )

        # 3. Semantic Validation
        if intent.side == "LONG":
            if q_sl >= q_entry:
                raise OrderValidationRejection(f"LONG stop {q_sl} >= entry {q_entry}")
            if q_tp and q_tp <= q_entry:
                raise OrderValidationRejection(f"LONG TP {q_tp} <= entry {q_entry}")
        else:
            if q_sl <= q_entry:
                raise OrderValidationRejection(f"SHORT stop {q_sl} <= entry {q_entry}")
            if q_tp and q_tp >= q_entry:
                raise OrderValidationRejection(f"SHORT TP {q_tp} >= entry {q_entry}")

        # 4. Risk Deviation Check
        original_risk = intent.original_qty * abs(intent.executable_entry - intent.effective_stop)
        quantized_risk = q_qty * abs(q_entry - q_sl)

        if original_risk > 0:
            deviation_bps = abs(quantized_risk - original_risk) / original_risk * Decimal("10000")
            if deviation_bps > self.policy.max_quantity_deviation_bps:
                raise OrderValidationRejection(
                    f"Risk deviation {deviation_bps:.2f} bps exceeds limit {self.policy.max_quantity_deviation_bps}"
                )

        # 5. Build ValidatedOrderSpec
        # Create a deterministic hash of the quantized values for the permit binding
        spec_payload = f"{q_qty}_{q_entry}_{q_sl}_{q_tp}"
        spec_hash = hashlib.sha256(spec_payload.encode("utf-8")).hexdigest()

        return ValidatedOrderSpec(
            intent_id=intent.intent_id,
            spec_hash=spec_hash,
            quantized_qty=q_qty,
            quantized_price=q_entry,
            quantized_stop=q_sl,
            quantized_tp=q_tp,
        )
