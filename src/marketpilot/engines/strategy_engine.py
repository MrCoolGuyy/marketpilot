"""
MarketPilot Engines � Strategy Engine.

Evaluates signals using a library of strategies and ranks them
based on Confidence, Market Quality, Regime Match, and Expected RR.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional

from marketpilot.config.settings import StrategySettings
from marketpilot.models.strategy import SignalDirection, StrategyEvaluation, StrategyResult
from marketpilot.models.scanner import InstrumentSnapshot
from marketpilot.models.indicators import IndicatorSeries
from marketpilot.models.regime import MarketRegime
from marketpilot.models.core import EngineMetadata

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    @abstractmethod
    def evaluate(
        self, 
        series: IndicatorSeries, 
        regime: MarketRegime, 
        snapshot: InstrumentSnapshot,
        settings: StrategySettings
    ) -> StrategyResult:
        """Evaluate the market data and explicitly return a StrategyResult."""
        pass


class EmaPullbackStrategy(BaseStrategy):
    """Buys in an uptrend when price pulls back to the fast EMA."""
    
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: InstrumentSnapshot, settings: StrategySettings) -> StrategyResult:
        point = series.latest
        if not point or point.ema_fast is None or point.ema_slow is None or point.atr is None or point.rsi is None:
            return StrategyResult(
                strategy_name="EMA Pullback",
                signal=SignalDirection.HOLD,
                reason_code="MISSING_INDICATORS"
            )

        signal = SignalDirection.HOLD
        confidence = Decimal("0")
        reason_code = "NO_PULLBACK_DETECTED"
        
        # Long Logic
        if regime in (MarketRegime.WEAK_BULL, MarketRegime.TRENDING_BULL) and point.ema_fast > point.ema_slow:
            # Price pulls back close to fast EMA
            dist_to_ema = (snapshot.last_price - point.ema_fast).copy_abs()
            if dist_to_ema < point.atr:
                signal = SignalDirection.LONG
                reason_code = "BULL_EMA_TOUCH"
                rsi_score = max(Decimal("0"), Decimal("100") - (point.rsi - Decimal("45")).copy_abs() * Decimal("5"))
                confidence = Decimal("30") + (rsi_score * Decimal("0.2")) + Decimal("30")
                
        # Short Logic
        elif regime in (MarketRegime.WEAK_BEAR, MarketRegime.TRENDING_BEAR) and point.ema_fast < point.ema_slow:
            dist_to_ema = (snapshot.last_price - point.ema_fast).copy_abs()
            if dist_to_ema < point.atr:
                signal = SignalDirection.SHORT
                reason_code = "BEAR_EMA_TOUCH"
                rsi_score = max(Decimal("0"), Decimal("100") - (point.rsi - Decimal("55")).copy_abs() * Decimal("5"))
                confidence = Decimal("30") + (rsi_score * Decimal("0.2")) + Decimal("30")

        metrics = {
            "RSI": f"{point.rsi:.2f}",
            "ATR": f"{point.atr:.2f}",
            "FastEMA": f"{point.ema_fast:.2f}"
        }

        if signal == SignalDirection.HOLD:
            if regime not in (MarketRegime.WEAK_BULL, MarketRegime.TRENDING_BULL, MarketRegime.WEAK_BEAR, MarketRegime.TRENDING_BEAR):
                reason_code = "REGIME_RANGING"

            return StrategyResult(
                strategy_name="EMA Pullback",
                signal=signal,
                reason_code=reason_code,
                metrics=metrics
            )

        # Risk parameters
        entry = snapshot.last_price
        sl_dist = point.atr * Decimal("1.5")
        
        if signal == SignalDirection.LONG:
            sl = entry - sl_dist
            tp = entry + (sl_dist * Decimal("3.0"))
        else:
            sl = entry + sl_dist
            tp = entry - (sl_dist * Decimal("3.0"))

        # Calculate RR
        risk = (entry - sl).copy_abs()
        reward = (tp - entry).copy_abs()
        expected_rr = reward / risk if risk > Decimal("0") else Decimal("0")
        
        confidence = min(Decimal("100"), max(Decimal("0"), confidence))

        candidate = StrategyEvaluation(
            expected_win_rate=Decimal("55.00"),
            entry_price=entry.quantize(Decimal("0.0001")),
            stop_loss=sl.quantize(Decimal("0.0001")),
            take_profit=tp.quantize(Decimal("0.0001")),
            expected_rr=expected_rr.quantize(Decimal("0.01"))
        )

        return StrategyResult(
            strategy_name="EMA Pullback",
            signal=signal,
            confidence=confidence.quantize(Decimal("0.01")),
            reason_code=reason_code,
            metrics=metrics,
            candidate_trade=candidate
        )


class MomentumStrategy(BaseStrategy):
    """Trades high momentum breakouts."""
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: InstrumentSnapshot, settings: StrategySettings) -> StrategyResult:
        point = series.latest
        if not point or point.rsi is None or point.atr is None:
            return StrategyResult(strategy_name="Momentum", signal=SignalDirection.HOLD, reason_code="MISSING_INDICATORS")
            
        signal = SignalDirection.HOLD
        confidence = Decimal("0")
        reason_code = "WEAK_MOMENTUM"
        
        if point.rsi > Decimal("65") and snapshot.momentum_24h > Decimal("0.05"):
            signal = SignalDirection.LONG
            reason_code = "STRONG_BULL_MOMENTUM"
            confidence = Decimal("75")
        elif point.rsi < Decimal("35") and snapshot.momentum_24h < Decimal("-0.05"):
            signal = SignalDirection.SHORT
            reason_code = "STRONG_BEAR_MOMENTUM"
            confidence = Decimal("75")
            
        metrics = {
            "RSI": f"{point.rsi:.2f}",
            "Momentum_24h": f"{snapshot.momentum_24h:.4f}"
        }

        if signal == SignalDirection.HOLD:
            return StrategyResult(strategy_name="Momentum", signal=signal, reason_code=reason_code, metrics=metrics)
            
        entry = snapshot.last_price
        sl_dist = point.atr * Decimal("2")
        if signal == SignalDirection.LONG:
            sl = entry - sl_dist
            tp = entry + (sl_dist * Decimal("2.1"))
        else:
            sl = entry + sl_dist
            tp = entry - (sl_dist * Decimal("2.1"))
            
        risk = (entry - sl).copy_abs()
        expected_rr = (tp - entry).copy_abs() / risk if risk > Decimal("0") else Decimal("0")
        
        candidate = StrategyEvaluation(
            expected_win_rate=Decimal("45.00"),
            entry_price=entry.quantize(Decimal("0.0001")),
            stop_loss=sl.quantize(Decimal("0.0001")),
            take_profit=tp.quantize(Decimal("0.0001")),
            expected_rr=expected_rr.quantize(Decimal("0.01"))
        )
        
        return StrategyResult(
            strategy_name="Momentum",
            signal=signal,
            confidence=confidence.quantize(Decimal("0.01")),
            reason_code=reason_code,
            metrics=metrics,
            candidate_trade=candidate
        )


class BreakoutStrategy(BaseStrategy):
    """Simple placeholder for breakout strategy."""
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: InstrumentSnapshot, settings: StrategySettings) -> StrategyResult:
        return StrategyResult(strategy_name="Breakout", signal=SignalDirection.HOLD, reason_code="NO_BREAKOUT_DETECTED")


class TrendFollowingStrategy(BaseStrategy):
    """Simple placeholder for trend following strategy."""
    def evaluate(self, series: IndicatorSeries, regime: MarketRegime, snapshot: InstrumentSnapshot, settings: StrategySettings) -> StrategyResult:
        return StrategyResult(strategy_name="Trend Following", signal=SignalDirection.HOLD, reason_code="TREND_EXHAUSTED")


class StrategyEngine:
    """Evaluates multiple strategies and selects the best one based on an Overall Score."""

    def __init__(self, settings: StrategySettings):
        self._settings = settings
        self._strategies: list[BaseStrategy] = [
            EmaPullbackStrategy(),
            MomentumStrategy(),
            BreakoutStrategy(),
            TrendFollowingStrategy()
        ]

    def _calculate_regime_match(self, result: StrategyResult, regime: MarketRegime) -> Decimal:
        """Scores how well the signal matches the current regime (0-100)."""
        if result.signal == SignalDirection.LONG:
            if regime in (MarketRegime.TRENDING_BULL, MarketRegime.WEAK_BULL):
                return Decimal("100")
            elif regime == MarketRegime.RANGING:
                return Decimal("50")
            else:
                return Decimal("0")
        elif result.signal == SignalDirection.SHORT:
            if regime in (MarketRegime.TRENDING_BEAR, MarketRegime.WEAK_BEAR):
                return Decimal("100")
            elif regime == MarketRegime.RANGING:
                return Decimal("50")
            else:
                return Decimal("0")
        return Decimal("0")

    def _normalize_rr(self, rr: Decimal) -> Decimal:
        """Normalizes RR to 0-100 score. E.g. RR 2.0 = 50, RR 4.0 = 100."""
        capped_rr = min(Decimal("4.0"), rr)
        score = (capped_rr / Decimal("4.0")) * Decimal("100")
        return score

    def evaluate(
        self, 
        series: IndicatorSeries, 
        regime: MarketRegime, 
        snapshot: InstrumentSnapshot,
        decision_id: str
    ) -> tuple[list[StrategyResult], Optional[StrategyResult], EngineMetadata]:
        """Evaluates all strategies and returns all results + the best one + metadata."""
        start_time = time.time()
        
        all_results: list[StrategyResult] = []
        best_result: Optional[StrategyResult] = None
        best_score = Decimal("-1")
        
        w_conf = Decimal(str(self._settings.weight_confidence))
        w_mq = Decimal(str(self._settings.weight_market_quality))
        w_reg = Decimal(str(self._settings.weight_regime_match))
        w_rr = Decimal(str(self._settings.weight_expected_rr))

        for strategy in self._strategies:
            res = strategy.evaluate(series, regime, snapshot, self._settings)
            all_results.append(res)
            
            if not res.is_actionable or not res.candidate_trade:
                continue
                
            # Must meet minimum RR
            if res.candidate_trade.expected_rr < Decimal(str(self._settings.minimum_rr)):
                # Overwrite reason if RR fails
                # Since frozen=True, we can't edit it. So we recreate it.
                res = StrategyResult(
                    **res.model_dump(exclude={"reason_code"}),
                    reason_code="REJECTED_LOW_RR"
                )
                # Note: modifying the list so the rejected one is returned
                all_results[-1] = res
                continue

            # Calculate components
            conf_score = res.confidence
            mq_score = snapshot.market_quality or Decimal("0")
            regime_score = self._calculate_regime_match(res, regime)
            rr_score = self._normalize_rr(res.candidate_trade.expected_rr)

            overall_score = (
                (conf_score * w_conf) +
                (mq_score * w_mq) +
                (regime_score * w_reg) +
                (rr_score * w_rr)
            )
            
            if overall_score > best_score:
                best_score = overall_score
                # Insert overall score into metrics for the best result?
                metrics = res.metrics.copy()
                metrics["overall_score"] = f"{overall_score:.2f}"
                best_result = StrategyResult(
                    **res.model_dump(exclude={"metrics"}),
                    metrics=metrics
                )
                
        processing_time_ms = (time.time() - start_time) * 1000
        metadata = EngineMetadata(processing_time_ms=processing_time_ms, decision_id=decision_id)
        
        return all_results, best_result, metadata

