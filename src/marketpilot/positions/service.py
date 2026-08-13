"""Position manager service."""

import math
from typing import Iterable
from decimal import Decimal

from marketpilot.models.paper import PaperPosition
from marketpilot.models.strategy import SignalDirection
from marketpilot.positions.models import PositionAction, PositionDecision

class PositionManagerService:
    """Evaluates positions against market prices safely."""
    
    def evaluate_positions(
        self, 
        positions: Iterable[PaperPosition], 
        prices: dict[str, Decimal]
    ) -> list[PositionDecision]:
        """
        Evaluate if any positions hit their target or stop-loss.
        Returns a list of PositionDecisions. Does NOT mutate anything.
        """
        decisions = []
        for pos in positions:
            mark_price = prices.get(pos.symbol)
            if mark_price is None or not mark_price.is_finite() or math.isnan(float(mark_price)):
                decisions.append(PositionDecision(
                    symbol=pos.symbol,
                    action=PositionAction.INVALID,
                    mark_price=None,
                    reason="missing_or_invalid_mark_price"
                ))
                continue
                
            if pos.stop_loss is None or pos.take_profit is None:
                decisions.append(PositionDecision(
                    symbol=pos.symbol,
                    action=PositionAction.HOLD,
                    mark_price=mark_price,
                    reason="missing_thresholds"
                ))
                continue
                
            # LONG logic
            if pos.direction == SignalDirection.LONG:
                if mark_price <= pos.stop_loss:
                    decisions.append(PositionDecision(
                        symbol=pos.symbol,
                        action=PositionAction.CLOSE_STOP_LOSS,
                        mark_price=mark_price,
                        reason="hit_stop_loss"
                    ))
                elif mark_price >= pos.take_profit:
                    decisions.append(PositionDecision(
                        symbol=pos.symbol,
                        action=PositionAction.CLOSE_TAKE_PROFIT,
                        mark_price=mark_price,
                        reason="hit_take_profit"
                    ))
                else:
                    decisions.append(PositionDecision(
                        symbol=pos.symbol,
                        action=PositionAction.HOLD,
                        mark_price=mark_price,
                        reason="within_bounds"
                    ))
                    
            # SHORT logic
            elif pos.direction == SignalDirection.SHORT:
                if mark_price >= pos.stop_loss:
                    decisions.append(PositionDecision(
                        symbol=pos.symbol,
                        action=PositionAction.CLOSE_STOP_LOSS,
                        mark_price=mark_price,
                        reason="hit_stop_loss"
                    ))
                elif mark_price <= pos.take_profit:
                    decisions.append(PositionDecision(
                        symbol=pos.symbol,
                        action=PositionAction.CLOSE_TAKE_PROFIT,
                        mark_price=mark_price,
                        reason="hit_take_profit"
                    ))
                else:
                    decisions.append(PositionDecision(
                        symbol=pos.symbol,
                        action=PositionAction.HOLD,
                        mark_price=mark_price,
                        reason="within_bounds"
                    ))
            else:
                decisions.append(PositionDecision(
                    symbol=pos.symbol,
                    action=PositionAction.INVALID,
                    mark_price=mark_price,
                    reason="invalid_direction"
                ))
                
        return decisions
