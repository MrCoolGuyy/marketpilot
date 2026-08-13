"""
MarketPilot Indicators — Service.

Computes technical indicators deterministically using pure Decimal arithmetic.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Sequence

from marketpilot.config.settings import IndicatorSettings
from marketpilot.models.indicators import IndicatorPoint, IndicatorSeries
from marketpilot.models.market import Kline


class IndicatorEngine:
    """Calculates technical indicators from Kline data.
    
    This service is strictly read-only and deterministic. It performs no network calls,
    mutates no input, and calculates purely in Decimal to avoid floating-point errors.
    """

    def __init__(self, settings: IndicatorSettings) -> None:
        self._settings = settings

    def calculate(self, klines: Sequence[Kline]) -> IndicatorSeries:
        """Calculate indicators for a series of Klines.
        
        Parameters
        ----------
        klines : Sequence[Kline]
            The historical kline data. Order does not strictly matter as it will be sorted
            chronologically internally.
            
        Returns
        -------
        IndicatorSeries
            An immutable series of indicator points aligned with the input candles.
            
        Raises
        ------
        ValueError
            If klines are empty, contain mixed symbols/intervals, or numerical data is invalid.
        """
        if not klines:
            raise ValueError("Cannot calculate indicators on empty kline list")

        # Sort chronologically to ensure deterministic calculation
        sorted_klines = sorted(klines, key=lambda k: k.open_time)
        
        # Validate homogeneity
        symbol = sorted_klines[0].symbol
        interval = sorted_klines[0].interval
        for k in sorted_klines:
            if k.symbol != symbol or k.interval != interval:
                raise ValueError("All klines must share the same symbol and interval")
                
        points: list[IndicatorPoint] = []

        # -- Running State --
        
        # EMA Fast & Slow
        ema_fast_mult = Decimal("2") / Decimal(str(self._settings.ema_fast + 1))
        ema_slow_mult = Decimal("2") / Decimal(str(self._settings.ema_slow + 1))
        ema_fast_acc = Decimal("0")
        ema_slow_acc = Decimal("0")
        prev_ema_fast: Decimal | None = None
        prev_ema_slow: Decimal | None = None
        
        # MACD
        macd_fast_mult = Decimal("2") / Decimal(str(self._settings.macd_fast + 1))
        macd_slow_mult = Decimal("2") / Decimal(str(self._settings.macd_slow + 1))
        macd_sig_mult = Decimal("2") / Decimal(str(self._settings.macd_signal + 1))
        macd_fast_acc = Decimal("0")
        macd_slow_acc = Decimal("0")
        prev_macd_fast: Decimal | None = None
        prev_macd_slow: Decimal | None = None
        macd_lines_history: list[Decimal] = []
        macd_sig_acc = Decimal("0")
        prev_macd_signal: Decimal | None = None
        
        # RSI
        rsi_period = self._settings.rsi_period
        prev_close_for_rsi: Decimal | None = None
        gains_acc = Decimal("0")
        losses_acc = Decimal("0")
        avg_gain: Decimal | None = None
        avg_loss: Decimal | None = None
        rsi_changes_count = 0
        
        # ATR
        atr_period = self._settings.atr_period
        prev_close_for_atr: Decimal | None = None
        tr_acc = Decimal("0")
        prev_atr: Decimal | None = None
        tr_count = 0
        
        # Volume SMA
        vol_period = self._settings.volume_sma_period
        volume_history: list[Decimal] = []
        
        # Session VWAP
        current_date = None
        cum_vol_price = Decimal("0")
        cum_vol = Decimal("0")

        # Start processing
        for i, k in enumerate(sorted_klines):
            try:
                close = Decimal(str(k.close))
                high = Decimal(str(k.high))
                low = Decimal(str(k.low))
                volume = Decimal(str(k.volume))
                
                for val in (close, high, low, volume):
                    if not val.is_finite():
                        raise ValueError(f"Value {val} is not finite")
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numerical data in kline at {k.open_time}: {exc}") from exc

            # ---------------------------------------------------------
            # 1. EMAs (Fast and Slow)
            # ---------------------------------------------------------
            current_ema_fast: Decimal | None = None
            if i < self._settings.ema_fast - 1:
                ema_fast_acc += close
            elif i == self._settings.ema_fast - 1:
                ema_fast_acc += close
                current_ema_fast = ema_fast_acc / Decimal(str(self._settings.ema_fast))
            else:
                if prev_ema_fast is not None:
                    current_ema_fast = (close * ema_fast_mult) + (prev_ema_fast * (Decimal("1") - ema_fast_mult))

            current_ema_slow: Decimal | None = None
            if i < self._settings.ema_slow - 1:
                ema_slow_acc += close
            elif i == self._settings.ema_slow - 1:
                ema_slow_acc += close
                current_ema_slow = ema_slow_acc / Decimal(str(self._settings.ema_slow))
            else:
                if prev_ema_slow is not None:
                    current_ema_slow = (close * ema_slow_mult) + (prev_ema_slow * (Decimal("1") - ema_slow_mult))

            prev_ema_fast = current_ema_fast
            prev_ema_slow = current_ema_slow

            # ---------------------------------------------------------
            # 2. MACD
            # ---------------------------------------------------------
            current_macd_fast: Decimal | None = None
            if i < self._settings.macd_fast - 1:
                macd_fast_acc += close
            elif i == self._settings.macd_fast - 1:
                macd_fast_acc += close
                current_macd_fast = macd_fast_acc / Decimal(str(self._settings.macd_fast))
            else:
                if prev_macd_fast is not None:
                    current_macd_fast = (close * macd_fast_mult) + (prev_macd_fast * (Decimal("1") - macd_fast_mult))
            prev_macd_fast = current_macd_fast

            current_macd_slow: Decimal | None = None
            if i < self._settings.macd_slow - 1:
                macd_slow_acc += close
            elif i == self._settings.macd_slow - 1:
                macd_slow_acc += close
                current_macd_slow = macd_slow_acc / Decimal(str(self._settings.macd_slow))
            else:
                if prev_macd_slow is not None:
                    current_macd_slow = (close * macd_slow_mult) + (prev_macd_slow * (Decimal("1") - macd_slow_mult))
            prev_macd_slow = current_macd_slow

            macd_line: Decimal | None = None
            macd_signal: Decimal | None = None
            macd_histogram: Decimal | None = None

            if current_macd_fast is not None and current_macd_slow is not None:
                macd_line = current_macd_fast - current_macd_slow
                macd_lines_history.append(macd_line)
                
                # Signal initialization requires MACD signal period count of macd_line values
                if len(macd_lines_history) < self._settings.macd_signal:
                    macd_sig_acc += macd_line
                elif len(macd_lines_history) == self._settings.macd_signal:
                    macd_sig_acc += macd_line
                    macd_signal = macd_sig_acc / Decimal(str(self._settings.macd_signal))
                    prev_macd_signal = macd_signal
                else:
                    if prev_macd_signal is not None:
                        macd_signal = (macd_line * macd_sig_mult) + (prev_macd_signal * (Decimal("1") - macd_sig_mult))
                        prev_macd_signal = macd_signal

                if macd_signal is not None:
                    macd_histogram = macd_line - macd_signal

            # ---------------------------------------------------------
            # 3. RSI
            # ---------------------------------------------------------
            rsi_val: Decimal | None = None
            if prev_close_for_rsi is not None:
                change = close - prev_close_for_rsi
                gain = change if change > Decimal("0") else Decimal("0")
                loss = -change if change < Decimal("0") else Decimal("0")
                
                rsi_changes_count += 1
                
                if rsi_changes_count < rsi_period:
                    gains_acc += gain
                    losses_acc += loss
                elif rsi_changes_count == rsi_period:
                    gains_acc += gain
                    losses_acc += loss
                    avg_gain = gains_acc / Decimal(str(rsi_period))
                    avg_loss = losses_acc / Decimal(str(rsi_period))
                else:
                    if avg_gain is not None and avg_loss is not None:
                        # Wilder smoothing
                        avg_gain = (avg_gain * Decimal(str(rsi_period - 1)) + gain) / Decimal(str(rsi_period))
                        avg_loss = (avg_loss * Decimal(str(rsi_period - 1)) + loss) / Decimal(str(rsi_period))
                
                if rsi_changes_count >= rsi_period and avg_gain is not None and avg_loss is not None:
                    if avg_loss == Decimal("0"):
                        if avg_gain > Decimal("0"):
                            rsi_val = Decimal("100")
                        else:
                            rsi_val = Decimal("50")
                    else:
                        rs = avg_gain / avg_loss
                        rsi_val = Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

            prev_close_for_rsi = close

            # ---------------------------------------------------------
            # 4. ATR
            # ---------------------------------------------------------
            atr_val: Decimal | None = None
            if prev_close_for_atr is None:
                tr = high - low
            else:
                tr = max(high - low, abs(high - prev_close_for_atr), abs(low - prev_close_for_atr))
            
            tr_count += 1
            if tr_count < atr_period:
                tr_acc += tr
            elif tr_count == atr_period:
                tr_acc += tr
                atr_val = tr_acc / Decimal(str(atr_period))
                prev_atr = atr_val
            else:
                if prev_atr is not None:
                    # Wilder smoothing for ATR: ATR_t = (ATR_{t-1} * (n-1) + TR_t) / n
                    atr_val = (prev_atr * Decimal(str(atr_period - 1)) + tr) / Decimal(str(atr_period))
                    prev_atr = atr_val
            
            prev_close_for_atr = close

            # ---------------------------------------------------------
            # 5. Volume SMA
            # ---------------------------------------------------------
            vol_sma_val: Decimal | None = None
            volume_history.append(volume)
            if len(volume_history) > vol_period:
                volume_history.pop(0)
            
            if len(volume_history) == vol_period:
                vol_sma_val = sum(volume_history) / Decimal(str(vol_period))

            # ---------------------------------------------------------
            # 6. Session VWAP (OHLC Approximation)
            # ---------------------------------------------------------
            candle_date = k.open_time.date()
            if current_date != candle_date:
                current_date = candle_date
                cum_vol_price = Decimal("0")
                cum_vol = Decimal("0")
            
            typical_price = (high + low + close) / Decimal("3")
            cum_vol_price += typical_price * volume
            cum_vol += volume
            
            session_vwap: Decimal | None = None
            if cum_vol > Decimal("0"):
                session_vwap = cum_vol_price / cum_vol

            # ---------------------------------------------------------
            # Assemble Point
            # ---------------------------------------------------------
            points.append(
                IndicatorPoint(
                    open_time=k.open_time,
                    ema_fast=current_ema_fast,
                    ema_slow=current_ema_slow,
                    rsi=rsi_val,
                    macd_line=macd_line,
                    macd_signal=macd_signal,
                    macd_histogram=macd_histogram,
                    atr=atr_val,
                    volume_sma=vol_sma_val,
                    session_vwap=session_vwap,
                )
            )

        return IndicatorSeries(
            symbol=symbol,
            interval=interval,
            points=tuple(points),
        )
