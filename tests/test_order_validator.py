"""Tests for Order Validator."""

import time
from decimal import Decimal
import pytest

from marketpilot.engines.order_validator import OrderValidator
from marketpilot.models.trade import TradePlan
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.models.strategy import SignalDirection
from marketpilot.models.regime import MarketRegime
from marketpilot.core.enums import AssetType

def test_order_validator_quantization() -> None:
    validator = OrderValidator()
    
    plan = TradePlan(
        decision_id="DEC-123",
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        entry=Decimal("100.12345"),
        sl=Decimal("90.98765"),
        tp=Decimal("120.11111"),
        qty=Decimal("0.12345"),
        risk=Decimal("100"),
        expected_rr=Decimal("2.0"),
        strategy="Test",
        confidence=Decimal("90"),
        market_regime=MarketRegime.TRENDING_BULL,
        market_quality=Decimal("90"),
        reason="Test",
        timestamp=time.time()
    )
    
    info = InstrumentInfo(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        status="Trading",
        tick_size="0.01",
        min_order_qty="0.001",
        max_order_qty="100",
        qty_step="0.001",
        min_leverage="1",
        max_leverage="100"
    )
    
    approved, new_plan, reason, meta = validator.validate(plan, info)
    
    assert approved
    assert new_plan is not None
    # qty 0.12345 snapped to 0.001 step -> 0.123
    assert new_plan.qty == Decimal("0.123")
    # prices snapped to 0.01 tick
    assert new_plan.entry == Decimal("100.12")
    assert new_plan.sl == Decimal("90.99")
    assert new_plan.tp == Decimal("120.11")

def test_order_validator_rejections() -> None:
    validator = OrderValidator()
    
    plan = TradePlan(
        decision_id="DEC-123",
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        entry=Decimal("100"),
        sl=Decimal("90"),
        tp=Decimal("120"),
        qty=Decimal("0.0001"), # Below min
        risk=Decimal("1"),
        expected_rr=Decimal("2.0"),
        strategy="Test",
        confidence=Decimal("90"),
        market_regime=MarketRegime.TRENDING_BULL,
        market_quality=Decimal("90"),
        reason="Test",
        timestamp=time.time()
    )
    
    info = InstrumentInfo(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        status="Trading",
        tick_size="0.01",
        min_order_qty="0.001",
        max_order_qty="100",
        qty_step="0.001",
        min_leverage="1",
        max_leverage="100"
    )
    
    # Below Min Qty
    approved, new_plan, reason, meta = validator.validate(plan, info)
    assert not approved
    assert "below min" in reason
    
    # Open Position
    plan.qty = Decimal("1")
    approved, new_plan, reason, meta = validator.validate(plan, info, has_open_position=True)
    assert not approved
    assert "open position" in reason
    
    # Notional < 5
    plan.qty = Decimal("0.01")
    plan.entry = Decimal("100") # 100 * 0.01 = 1.0 < 5.0
    approved, new_plan, reason, meta = validator.validate(plan, info)
    assert not approved
    assert "Notional value" in reason
    
    # Status
    plan.qty = Decimal("1")
    info_closed = InstrumentInfo(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        status="Closed",
        tick_size="0.01",
        min_order_qty="0.001",
        max_order_qty="100",
        qty_step="0.001",
        min_leverage="1",
        max_leverage="100"
    )
    approved, new_plan, reason, meta = validator.validate(plan, info_closed)
    assert not approved
    assert "status is Closed" in reason
