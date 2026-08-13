"""
MarketPilot Telegram — Typed notification events.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Union

from pydantic import BaseModel, Field

from marketpilot.models.strategy import SignalDirection


class BaseNotification(BaseModel):
    """Base model for Telegram notifications."""
    
    def render(self) -> str:
        """Render the notification to a safe, plain text string."""
        raise NotImplementedError


class PaperPositionOpenedEvent(BaseNotification):
    type: Literal["paper_opened"] = "paper_opened"
    symbol: str
    direction: SignalDirection
    quantity: Decimal
    entry_price: Decimal
    
    def render(self) -> str:
        return (
            f"🟢 [PAPER ONLY] Position Opened\n\n"
            f"Symbol: {self.symbol}\n"
            f"Direction: {self.direction.value}\n"
            f"Qty: {self.quantity:.4f}\n"
            f"Entry: {self.entry_price:.4f}\n\n"
            f"No real order was placed."
        )


class PaperPositionClosedEvent(BaseNotification):
    type: Literal["paper_closed"] = "paper_closed"
    symbol: str
    direction: SignalDirection
    exit_price: Decimal
    net_pnl: Decimal
    
    def render(self) -> str:
        pnl_icon = "🟩" if self.net_pnl > 0 else ("🟥" if self.net_pnl < 0 else "⬜")
        return (
            f"🔴 [PAPER ONLY] Position Closed\n\n"
            f"Symbol: {self.symbol}\n"
            f"Direction: {self.direction.value}\n"
            f"Exit: {self.exit_price:.4f}\n"
            f"Net PnL: {pnl_icon} {self.net_pnl:.4f}\n\n"
            f"No real order was placed."
        )


class PaperActionRejectedEvent(BaseNotification):
    type: Literal["paper_rejected"] = "paper_rejected"
    symbol: str
    action: str
    reason: str
    
    def render(self) -> str:
        return (
            f"⚠️ [PAPER ONLY] Action Rejected\n\n"
            f"Symbol: {self.symbol}\n"
            f"Action: {self.action}\n"
            f"Reason: {self.reason}\n\n"
            f"No real order was placed."
        )


class HistoricalRunCompletedEvent(BaseNotification):
    type: Literal["historical_completed"] = "historical_completed"
    run_type: Literal["backtest", "optimize"]
    symbol: str
    interval: str
    total_return_pct: Decimal | None = None
    best_candidate_label: str | None = None
    
    def render(self) -> str:
        lines = [
            f"📊 [HISTORICAL ONLY] Run Completed\n",
            f"Type: {self.run_type.capitalize()}",
            f"Symbol: {self.symbol} ({self.interval})"
        ]
        if self.run_type == "backtest" and self.total_return_pct is not None:
            lines.append(f"Total Return: {self.total_return_pct:.2f}%")
        elif self.run_type == "optimize" and self.best_candidate_label:
            lines.append(f"Best: {self.best_candidate_label}")
            
        return "\n".join(lines)


AnyNotification = Union[
    PaperPositionOpenedEvent,
    PaperPositionClosedEvent,
    PaperActionRejectedEvent,
    HistoricalRunCompletedEvent,
]
