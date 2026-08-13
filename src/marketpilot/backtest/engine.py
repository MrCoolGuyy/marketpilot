"""
MarketPilot Backtest — Simulation Engine.

A deterministic, in-memory historical simulator that replays market data over the existing
Indicators, Strategy, and Risk Manager pipeline while evaluating exact fills and stop-out rules.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from marketpilot.config.settings import BacktestSettings
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.backtest import BacktestMetrics, BacktestResult, BacktestTrade
from marketpilot.models.market import Kline
from marketpilot.models.indicators import IndicatorSeries
from marketpilot.models.risk import RiskAssessment
from marketpilot.models.strategy import SignalDirection, StrategySignal
from marketpilot.risk.service import RiskManagerService
from marketpilot.strategy.service import StrategyService


class BacktestEngine:
    """Historical backtesting engine."""

    def __init__(
        self,
        settings: BacktestSettings,
        indicator_service: IndicatorService,
        strategy_service: StrategyService,
        risk_service: RiskManagerService,
    ) -> None:
        self._settings = settings
        self._indicator_service = indicator_service
        self._strategy_service = strategy_service
        self._risk_service = risk_service

    def run(self, klines: Sequence[Kline], trading_start_index: int = 0) -> BacktestResult:
        """Run the backtest over the provided chronological closed klines."""
        if not klines:
            raise ValueError("No klines provided for backtesting")

        symbol = klines[0].symbol
        interval = klines[0].interval

        # Input validation and normalization without mutating the original sequence
        valid_klines = []
        for k in klines:
            if k.symbol != symbol or k.interval != interval:
                raise ValueError("Mixed symbols or intervals in klines")
            if not k.is_closed:
                raise ValueError("Open klines are not permitted for backtesting")
            valid_klines.append(k)

        # Ensure sorted chronologically
        valid_klines.sort(key=lambda k: k.open_time)

        if trading_start_index < 0 or trading_start_index >= len(valid_klines):
            if not (trading_start_index == 0 and len(valid_klines) == 0):
                raise ValueError(f"trading_start_index {trading_start_index} out of bounds")

        start_time = valid_klines[trading_start_index].open_time
        end_time = valid_klines[-1].open_time

        # Pre-calculate indicators for the entire dataset to avoid O(N^2) runtime.
        full_series = self._indicator_service.calculate(valid_klines)

        equity = Decimal(str(self._settings.initial_equity))
        starting_equity = equity

        trades: list[BacktestTrade] = []
        equity_curve: list[Decimal] = [equity]  # starts before first candle

        # Active position state
        active_direction: SignalDirection | None = None
        entry_price: Decimal | None = None
        entry_time: datetime | None = None
        signal_time: datetime | None = None
        quantity: Decimal | None = None
        entry_fee: Decimal | None = None
        stop_loss: Decimal | None = None
        take_profit: Decimal | None = None
        initial_margin: Decimal | None = None

        # Pending actions to execute at next open
        pending_close: bool = False
        pending_open: StrategySignal | None = None

        # Helper to compute fee and slippage exactly like Paper Trading
        def get_slipped_price(raw_price: Decimal | str, direction: SignalDirection, is_entry: bool) -> Decimal:
            price = Decimal(str(raw_price))
            slip_ratio = Decimal(str(self._settings.slippage_bps)) / Decimal("10000")
            if (direction == SignalDirection.LONG and is_entry) or (direction == SignalDirection.SHORT and not is_entry):
                # Buying: price goes up
                return price * (Decimal("1") + slip_ratio)
            else:
                # Selling: price goes down
                return price * (Decimal("1") - slip_ratio)

        for i in range(trading_start_index, len(valid_klines)):
            kline = valid_klines[i]
            
            # Slice series strictly up to the PREVIOUS candle for pending action assessment
            # Wait, IndicatorSeries is needed for ATR when opening. ATR from the PREVIOUS candle is used.
            prev_series = IndicatorSeries(
                symbol=symbol,
                interval=interval,
                points=full_series.points[:i]
            )

            # 1. Execute Pending Actions at the open of the current candle
            if pending_close and active_direction is not None and entry_price is not None and quantity is not None and entry_fee is not None:
                # Execute opposite signal close at this candle's open
                slipped_exit = get_slipped_price(kline.open, active_direction, is_entry=False)
                exit_notional = quantity * slipped_exit
                exit_fee = exit_notional * Decimal(str(self._settings.taker_fee_fraction))
                
                if active_direction == SignalDirection.LONG:
                    gross_pnl = (slipped_exit - entry_price) * quantity
                else:
                    gross_pnl = (entry_price - slipped_exit) * quantity
                    
                realized = gross_pnl - entry_fee - exit_fee
                equity += realized
                
                trades.append(BacktestTrade(
                    direction=active_direction,
                    signal_time=signal_time,  # type: ignore
                    entry_time=entry_time,  # type: ignore
                    exit_time=kline.open_time,
                    entry_price=entry_price,
                    exit_price=slipped_exit,
                    quantity=quantity,
                    entry_fee=entry_fee,
                    exit_fee=exit_fee,
                    realized_pnl=realized,
                    exit_reason="opposite_signal"
                ))
                
                active_direction = None
                entry_price = None
                entry_time = None
                signal_time = None
                quantity = None
                entry_fee = None
                stop_loss = None
                take_profit = None
                initial_margin = None
                pending_close = False

            if pending_open is not None and active_direction is None:
                # Execute open at this candle's open
                slipped_entry = get_slipped_price(kline.open, pending_open.direction, is_entry=True)
                atr = prev_series.latest.atr if prev_series.latest else None
                if atr is not None:
                    assessment = self._risk_service.assess(
                        signal=pending_open,
                        entry_price=slipped_entry,
                        atr=atr,
                        account_equity=equity
                    )
                    if assessment.eligible_for_paper_trading and assessment.theoretical_quantity and assessment.stop_loss and assessment.take_profit:
                        qty = assessment.theoretical_quantity
                        notional = qty * slipped_entry
                        fee = notional * Decimal(str(self._settings.taker_fee_fraction))
                        margin = notional / Decimal(str(self._settings.leverage))
                        req_cash = margin + fee
                        if equity >= req_cash:
                            active_direction = pending_open.direction
                            entry_price = slipped_entry
                            entry_time = kline.open_time
                            signal_time = pending_open.open_time
                            quantity = qty
                            entry_fee = fee
                            stop_loss = assessment.stop_loss
                            take_profit = assessment.take_profit
                            initial_margin = margin
                pending_open = None

            # Clear any stale pending open just in case
            pending_open = None
            pending_close = False

            # 2. Check for stop-loss or take-profit hits intrabar
            if active_direction is not None and entry_price is not None and quantity is not None and entry_fee is not None and stop_loss is not None and take_profit is not None:
                hit_stop = False
                hit_target = False
                
                if active_direction == SignalDirection.LONG:
                    if Decimal(kline.low) <= stop_loss:
                        hit_stop = True
                    if Decimal(kline.high) >= take_profit:
                        hit_target = True
                else:
                    if Decimal(kline.high) >= stop_loss:
                        hit_stop = True
                    if Decimal(kline.low) <= take_profit:
                        hit_target = True
                
                # Priority: If both hit, conservative rule applies (stop loss wins)
                exit_reason = None
                exit_trigger_price = None
                if hit_stop:
                    exit_reason = "stop_loss"
                    exit_trigger_price = stop_loss
                elif hit_target:
                    exit_reason = "take_profit"
                    exit_trigger_price = take_profit

                if exit_reason and exit_trigger_price:
                    slipped_exit = get_slipped_price(exit_trigger_price, active_direction, is_entry=False)
                    exit_notional = quantity * slipped_exit
                    exit_fee = exit_notional * Decimal(str(self._settings.taker_fee_fraction))
                    
                    if active_direction == SignalDirection.LONG:
                        gross_pnl = (slipped_exit - entry_price) * quantity
                    else:
                        gross_pnl = (entry_price - slipped_exit) * quantity
                        
                    realized = gross_pnl - entry_fee - exit_fee
                    equity += realized
                    
                    trades.append(BacktestTrade(
                        direction=active_direction,
                        signal_time=signal_time,  # type: ignore
                        entry_time=entry_time,  # type: ignore
                        exit_time=kline.open_time,
                        entry_price=entry_price,
                        exit_price=slipped_exit,
                        quantity=quantity,
                        entry_fee=entry_fee,
                        exit_fee=exit_fee,
                        realized_pnl=realized,
                        exit_reason=exit_reason
                    ))
                    
                    active_direction = None
                    entry_price = None
                    entry_time = None
                    signal_time = None
                    quantity = None
                    entry_fee = None
                    stop_loss = None
                    take_profit = None
                    initial_margin = None

            # 3. Evaluate strategy signal at current candle close
            current_series = IndicatorSeries(
                symbol=symbol,
                interval=interval,
                points=full_series.points[:i+1]
            )
            signal = self._strategy_service.evaluate(current_series)
            
            # 4. Schedule actions for next open
            if active_direction is not None:
                if signal.score == Decimal("100") and signal.direction != active_direction and signal.direction != SignalDirection.NEUTRAL:
                    pending_close = True
                    # Also queue the opposite side to open
                    pending_open = signal
            elif active_direction is None:
                if signal.score == Decimal("100") and signal.direction != SignalDirection.NEUTRAL:
                    pending_open = signal

            # 5. Append MTM or realized equity to the equity curve for this candle
            mtm_equity = equity
            if active_direction is not None and entry_price is not None and quantity is not None and entry_fee is not None:
                # Mark to market using close price
                exit_price = get_slipped_price(kline.close, active_direction, is_entry=False)
                notional = quantity * exit_price
                exit_fee_mtm = notional * Decimal(str(self._settings.taker_fee_fraction))
                if active_direction == SignalDirection.LONG:
                    gross_pnl = (exit_price - entry_price) * quantity
                else:
                    gross_pnl = (entry_price - exit_price) * quantity
                mtm_equity = equity + gross_pnl - entry_fee - exit_fee_mtm
            
            equity_curve.append(mtm_equity)

        # End of data - close open positions
        if active_direction is not None and entry_price is not None and quantity is not None and entry_fee is not None:
            final_close = valid_klines[-1].close
            slipped_exit = get_slipped_price(final_close, active_direction, is_entry=False)
            exit_notional = quantity * slipped_exit
            exit_fee = exit_notional * Decimal(str(self._settings.taker_fee_fraction))
            
            if active_direction == SignalDirection.LONG:
                gross_pnl = (slipped_exit - entry_price) * quantity
            else:
                gross_pnl = (entry_price - slipped_exit) * quantity
                
            realized = gross_pnl - entry_fee - exit_fee
            equity += realized
            
            trades.append(BacktestTrade(
                direction=active_direction,
                signal_time=signal_time,  # type: ignore
                entry_time=entry_time,  # type: ignore
                exit_time=klines[-1].open_time,
                entry_price=entry_price,
                exit_price=slipped_exit,
                quantity=quantity,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                realized_pnl=realized,
                exit_reason="end_of_data"
            ))

            # Need to update the last MTM value in equity_curve to match realized
            equity_curve[-1] = equity

        # Calculate Metrics
        win_count = sum(1 for t in trades if t.realized_pnl > Decimal("0"))
        loss_count = sum(1 for t in trades if t.realized_pnl <= Decimal("0"))
        gross_profit = sum((t.realized_pnl for t in trades if t.realized_pnl > Decimal("0")), Decimal("0"))
        gross_loss = sum((abs(t.realized_pnl) for t in trades if t.realized_pnl <= Decimal("0")), Decimal("0"))

        win_rate = None
        if len(trades) > 0:
            win_rate = Decimal(str(win_count)) / Decimal(str(len(trades)))

        profit_factor = None
        if gross_loss > Decimal("0"):
            profit_factor = gross_profit / gross_loss

        total_return_fraction = (equity / starting_equity) - Decimal("1")
        
        # Max Drawdown
        max_equity = starting_equity
        max_drawdown = Decimal("0")
        for eq in equity_curve:
            if eq > max_equity:
                max_equity = eq
            drawdown = (max_equity - eq) / max_equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        metrics = BacktestMetrics(
            starting_equity=starting_equity,
            ending_equity=equity,
            total_return_fraction=total_return_fraction,
            max_drawdown_fraction=max_drawdown,
            trade_count=len(trades),
            win_rate=win_rate,
            profit_factor=profit_factor
        )

        return BacktestResult(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            metrics=metrics
        )
