"""
MarketPilot Paper Trading — Service.

Local simulator for perpetual USDT-linear trades without exchange execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from marketpilot.config.settings import PaperSettings
from marketpilot.models.paper import PaperAccountSnapshot, PaperPosition, PaperTrade
from marketpilot.models.risk import RiskAssessment
from marketpilot.models.strategy import SignalDirection
from marketpilot.storage.repository import PaperAccountRepository
from marketpilot.storage.tables import PaperAccountRecord, PaperPositionRecord, PaperTradeRecord


class PaperTradingService:
    """Service to handle simulated paper trading operations."""

    def __init__(self, settings: PaperSettings) -> None:
        self._settings = settings

    async def get_snapshot(self, session: AsyncSession, market_prices: dict[str, Decimal]) -> PaperAccountSnapshot:
        """Fetch the complete account snapshot and evaluate mark-to-market."""
        repo = PaperAccountRepository(session)
        acc = await repo.get_account()
        
        if acc is None:
            return PaperAccountSnapshot(
                cash=self._settings.initial_equity,
                locked_margin=Decimal("0"),
                equity=self._settings.initial_equity,
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                positions=(),
                trades=()
            )

        pos_records = await repo.get_positions()
        trade_records = await repo.get_trades()

        unrealized_pnl = Decimal("0")
        positions = []
        
        for p in pos_records:
            mark = market_prices.get(p.symbol, Decimal(p.entry_price))
            qty = Decimal(p.quantity)
            entry = Decimal(p.entry_price)
            
            if p.direction == SignalDirection.LONG.value:
                pnl = (mark - entry) * qty
            else:
                pnl = (entry - mark) * qty
                
            unrealized_pnl += pnl
            
            positions.append(PaperPosition(
                symbol=p.symbol,
                direction=SignalDirection(p.direction),
                quantity=qty,
                entry_price=entry,
                mark_price=mark,
                leverage=p.leverage,
                initial_margin=Decimal(p.initial_margin),
                stop_loss=Decimal(p.stop_loss) if p.stop_loss else None,
                take_profit=Decimal(p.take_profit) if p.take_profit else None,
                entry_fee=Decimal(p.entry_fee),
                unrealized_pnl=pnl
            ))
            
        trades = []
        for t in trade_records:
            trades.append(PaperTrade(
                id=t.id,
                symbol=t.symbol,
                direction=SignalDirection(t.direction),
                quantity=Decimal(t.quantity),
                entry_price=Decimal(t.entry_price),
                entry_fee=Decimal(t.entry_fee),
                exit_price=Decimal(t.exit_price) if t.exit_price else None,
                exit_fee=Decimal(t.exit_fee) if t.exit_fee else None,
                opened_at=t.opened_at,
                closed_at=t.closed_at,
                realized_pnl=Decimal(t.realized_pnl) if t.realized_pnl else None,
                status=t.status
            ))

        cash = Decimal(acc.cash)
        locked = Decimal(acc.locked_margin)
        realized = Decimal(acc.realized_pnl)

        return PaperAccountSnapshot(
            cash=cash,
            locked_margin=locked,
            equity=cash + locked + unrealized_pnl,
            realized_pnl=realized,
            unrealized_pnl=unrealized_pnl,
            positions=tuple(positions),
            trades=tuple(trades)
        )

    async def open_position(self, session: AsyncSession, assessment: RiskAssessment, market_price: Decimal) -> PaperTrade:
        """Open a new simulated position from a risk assessment."""
        if not assessment.eligible_for_paper_trading or assessment.direction == SignalDirection.NEUTRAL:
            raise ValueError(f"Assessment is not eligible for paper trading: {assessment.reasons}")
            
        repo = PaperAccountRepository(session)
        acc = await repo.get_account()
        if not acc:
            await repo.reset(str(self._settings.initial_equity))
            acc = await repo.get_account()
            
        if not acc:
            raise ValueError("Failed to initialize paper account")

        existing = await repo.get_position_by_symbol(assessment.symbol)
        if existing:
            raise ValueError(f"A position for {assessment.symbol} is already open")

        qty = assessment.theoretical_quantity
        if qty is None:
            raise ValueError("Missing theoretical quantity")
            
        # Slippage calculation
        slip_ratio = self._settings.slippage_bps / Decimal("10000")
        if assessment.direction == SignalDirection.LONG:
            fill_price = market_price * (Decimal("1") + slip_ratio)
        else:
            fill_price = market_price * (Decimal("1") - slip_ratio)

        notional = qty * fill_price
        initial_margin = notional / Decimal(self._settings.leverage)
        entry_fee = notional * self._settings.taker_fee_fraction
        
        required_cash = initial_margin + entry_fee
        cash = Decimal(acc.cash)
        
        if required_cash > cash:
            raise ValueError(f"Insufficient cash: require {required_cash}, have {cash}")

        # Mutate account
        acc.cash = str(cash - required_cash)
        acc.locked_margin = str(Decimal(acc.locked_margin) + initial_margin)
        
        trade_id = str(uuid.uuid4())
        now = datetime.now(tz=UTC)
        
        pos = PaperPositionRecord(
            symbol=assessment.symbol,
            direction=assessment.direction.value,
            quantity=str(qty),
            entry_price=str(fill_price),
            leverage=self._settings.leverage,
            initial_margin=str(initial_margin),
            stop_loss=str(assessment.stop_loss) if assessment.stop_loss else None,
            take_profit=str(assessment.take_profit) if assessment.take_profit else None,
            entry_fee=str(entry_fee)
        )
        
        trade_rec = PaperTradeRecord(
            id=trade_id,
            symbol=assessment.symbol,
            direction=assessment.direction.value,
            quantity=str(qty),
            entry_price=str(fill_price),
            entry_fee=str(entry_fee),
            opened_at=now,
            status="OPEN"
        )
        
        await repo.save_account(acc)
        await repo.save_position(pos)
        await repo.save_trade(trade_rec)
        
        return PaperTrade(
            id=trade_id,
            symbol=assessment.symbol,
            direction=assessment.direction,
            quantity=qty,
            entry_price=fill_price,
            entry_fee=entry_fee,
            opened_at=now,
            status="OPEN"
        )

    async def close_position(self, session: AsyncSession, symbol: str, market_price: Decimal, exit_reason: str = "manual_close") -> PaperTrade:
        """Close an existing position."""
        repo = PaperAccountRepository(session)
        pos = await repo.get_position_by_symbol(symbol)
        
        if not pos:
            raise ValueError(f"No open position found for {symbol}")
            
        acc = await repo.get_account()
        if not acc:
            raise ValueError("Account state not found")
            
        qty = Decimal(pos.quantity)
        entry_price = Decimal(pos.entry_price)
        
        # Slippage calculation for exit
        slip_ratio = self._settings.slippage_bps / Decimal("10000")
        if pos.direction == SignalDirection.LONG.value:
            # We sell to close a long, so slippage reduces price
            exit_price = market_price * (Decimal("1") - slip_ratio)
            gross_pnl = (exit_price - entry_price) * qty
        else:
            # We buy to close a short, so slippage increases price
            exit_price = market_price * (Decimal("1") + slip_ratio)
            gross_pnl = (entry_price - exit_price) * qty
            
        exit_notional = qty * exit_price
        exit_fee = exit_notional * self._settings.taker_fee_fraction
        
        entry_fee = Decimal(pos.entry_fee)
        net_pnl = gross_pnl - entry_fee - exit_fee
        
        locked_margin = Decimal(pos.initial_margin)
        
        acc.cash = str(Decimal(acc.cash) + locked_margin + gross_pnl - exit_fee)
        acc.locked_margin = str(Decimal(acc.locked_margin) - locked_margin)
        acc.realized_pnl = str(Decimal(acc.realized_pnl) + net_pnl)
        
        # Find open trade to close it
        trades = await repo.get_trades()
        open_trade = None
        for t in trades:
            if t.symbol == symbol and t.status == "OPEN":
                open_trade = t
                break
                
        if open_trade:
            open_trade.exit_price = str(exit_price)
            open_trade.exit_fee = str(exit_fee)
            open_trade.closed_at = datetime.now(tz=UTC)
            open_trade.realized_pnl = str(net_pnl)
            open_trade.exit_reason = exit_reason
            open_trade.status = "CLOSED"
            await repo.save_trade(open_trade)
        else:
            raise ValueError(f"No open trade found for {symbol} to close")
            
        await repo.save_account(acc)
        await repo.delete_position(pos)
        
        if open_trade:
            return PaperTrade(
                id=open_trade.id,
                symbol=open_trade.symbol,
                direction=SignalDirection(open_trade.direction),
                quantity=qty,
                entry_price=entry_price,
                entry_fee=entry_fee,
                exit_price=exit_price,
                exit_fee=exit_fee,
                opened_at=open_trade.opened_at,
                closed_at=open_trade.closed_at,
                realized_pnl=net_pnl,
                status="CLOSED",
                exit_reason=exit_reason
            )
        raise ValueError("Could not find matching trade to close")

    async def reset(self, session: AsyncSession) -> None:
        """Reset paper trading state fully."""
        repo = PaperAccountRepository(session)
        await repo.reset(str(self._settings.initial_equity))
