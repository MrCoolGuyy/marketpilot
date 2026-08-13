"""Tests for Position Manager."""

from decimal import Decimal
from marketpilot.models.paper import PaperPosition
from marketpilot.models.strategy import SignalDirection
from marketpilot.positions.models import PositionAction
from marketpilot.positions.service import PositionManagerService

def test_evaluate_long():
    manager = PositionManagerService()
    pos = PaperPosition(
        symbol="BTCUSDT", direction=SignalDirection.LONG,
        quantity=Decimal("1"), entry_price=Decimal("1000"),
        mark_price=Decimal("1000"), leverage=1, initial_margin=Decimal("1000"),
        stop_loss=Decimal("900"), take_profit=Decimal("1100"), entry_fee=Decimal("1")
    )
    
    # HOLD within bounds
    decisions = manager.evaluate_positions([pos], {"BTCUSDT": Decimal("1000")})
    assert len(decisions) == 1
    assert decisions[0].action == PositionAction.HOLD
    
    # CLOSE_STOP_LOSS
    decisions = manager.evaluate_positions([pos], {"BTCUSDT": Decimal("900")})
    assert decisions[0].action == PositionAction.CLOSE_STOP_LOSS
    assert decisions[0].reason == "hit_stop_loss"
    
    # CLOSE_TAKE_PROFIT
    decisions = manager.evaluate_positions([pos], {"BTCUSDT": Decimal("1100")})
    assert decisions[0].action == PositionAction.CLOSE_TAKE_PROFIT
    assert decisions[0].reason == "hit_take_profit"

def test_evaluate_short():
    manager = PositionManagerService()
    pos = PaperPosition(
        symbol="ETHUSDT", direction=SignalDirection.SHORT,
        quantity=Decimal("1"), entry_price=Decimal("2000"),
        mark_price=Decimal("2000"), leverage=1, initial_margin=Decimal("2000"),
        stop_loss=Decimal("2100"), take_profit=Decimal("1900"), entry_fee=Decimal("1")
    )
    
    # HOLD within bounds
    decisions = manager.evaluate_positions([pos], {"ETHUSDT": Decimal("2000")})
    assert decisions[0].action == PositionAction.HOLD
    
    # CLOSE_STOP_LOSS (price goes up)
    decisions = manager.evaluate_positions([pos], {"ETHUSDT": Decimal("2100")})
    assert decisions[0].action == PositionAction.CLOSE_STOP_LOSS
    
    # CLOSE_TAKE_PROFIT (price goes down)
    decisions = manager.evaluate_positions([pos], {"ETHUSDT": Decimal("1900")})
    assert decisions[0].action == PositionAction.CLOSE_TAKE_PROFIT

def test_evaluate_invalid_missing():
    manager = PositionManagerService()
    pos = PaperPosition(
        symbol="SOLUSDT", direction=SignalDirection.LONG,
        quantity=Decimal("1"), entry_price=Decimal("100"),
        mark_price=Decimal("100"), leverage=1, initial_margin=Decimal("100"),
        stop_loss=None, take_profit=None, entry_fee=Decimal("1")
    )
    
    # Missing market price
    decisions = manager.evaluate_positions([pos], {})
    assert decisions[0].action == PositionAction.INVALID
    assert decisions[0].reason == "missing_or_invalid_mark_price"
    
    # Missing thresholds
    decisions = manager.evaluate_positions([pos], {"SOLUSDT": Decimal("150")})
    assert decisions[0].action == PositionAction.HOLD
    assert decisions[0].reason == "missing_thresholds"
