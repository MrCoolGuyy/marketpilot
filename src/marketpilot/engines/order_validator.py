"""
MarketPilot Engines � Order Validator.

Ensures that a TradePlan conforms to the exchange's strict instrument rules
such as tick size, qty step, min/max limits, and market status.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional

from marketpilot.models.trade import TradePlan
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.models.core import EngineMetadata

class OrderValidator:
    """Validates and quantizes TradePlans before execution."""

    def _snap_to_step(self, value: Decimal, step_size: Decimal) -> Decimal:
        """Snap a value down to the nearest multiple of step_size."""
        if step_size == Decimal("0"):
            return value
        # Divide, floor, multiply back
        steps = value // step_size
        return steps * step_size

    def _snap_price(self, price: Decimal, tick_size: Decimal) -> Decimal:
        """Snap a price to the nearest tick."""
        if tick_size == Decimal("0"):
            return price
        # Standard rounding for price
        ticks = (price / tick_size).quantize(Decimal("1"))
        return ticks * tick_size

    def validate(
        self, 
        plan: TradePlan, 
        instrument: InstrumentInfo, 
        has_open_position: bool = False
    ) -> tuple[bool, Optional[TradePlan], str, EngineMetadata]:
        """Validate and snap a TradePlan according to exchange rules."""
        start_time = time.time()
        
        # 1. Market Status
        if instrument.status.lower() != "trading":
            meta = EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000)
            return False, None, f"Instrument status is {instrument.status}", meta

        # 2. Duplicate Order / Position
        if has_open_position:
            meta = EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000)
            return False, None, "An open position already exists for this symbol.", meta

        # 3. Quantize Qty
        qty_step = Decimal(instrument.qty_step)
        min_qty = Decimal(instrument.min_order_qty)
        max_qty = Decimal(instrument.max_order_qty) if instrument.max_order_qty else Decimal("Inf")
        
        snapped_qty = self._snap_to_step(plan.qty, qty_step)
        
        if snapped_qty < min_qty:
            meta = EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000)
            return False, None, f"Quantity {snapped_qty} is below min {min_qty}", meta
            
        if snapped_qty > max_qty:
            meta = EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000)
            return False, None, f"Quantity {snapped_qty} is above max {max_qty}", meta

        # 4. Quantize Prices
        tick_size = Decimal(instrument.tick_size)
        snapped_entry = self._snap_price(plan.entry, tick_size)
        snapped_sl = self._snap_price(plan.sl, tick_size)
        snapped_tp = self._snap_price(plan.tp, tick_size)

        # 5. Check min order value (often 5 USDT on Bybit)
        notional = snapped_qty * snapped_entry
        if notional < Decimal("5.0"):
            meta = EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000)
            return False, None, f"Notional value {notional:.2f} is below 5 USDT minimum.", meta

        # Build final quantized plan
        quantized_plan = TradePlan(
            **plan.model_dump(exclude={"entry", "sl", "tp", "qty"}),
            entry=snapped_entry,
            sl=snapped_sl,
            tp=snapped_tp,
            qty=snapped_qty
        )

        meta = EngineMetadata(processing_time_ms=(time.time() - start_time) * 1000)
        return True, quantized_plan, "Validation passed", meta
