"""MarketPilot Research — Service for capture, evaluation, and reporting."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Sequence

from marketpilot.config.settings import AppSettings
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.market import Kline
from marketpilot.models.research import ResearchObservation, ResearchOutcome, ResearchReport
from marketpilot.models.strategy import SignalDirection
from marketpilot.research.store import ResearchStore
from marketpilot.risk.service import RiskManagerService
from marketpilot.strategy.service import StrategyService

class ResearchService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.store = ResearchStore()
        
    def capture(self, klines: Sequence[Kline], theoretical_equity: Decimal) -> ResearchObservation | None:
        """Evaluate strictly historical klines and capture an observation if eligible."""
        if not klines:
            return None
            
        # Ensure klines are sorted chronologically and closed
        valid_klines = [k for k in klines if k.is_closed]
        valid_klines.sort(key=lambda k: k.open_time)
        
        if not valid_klines:
            return None
            
        # Indicator calculation over the dataset
        ind_service = IndicatorService(self.settings.indicators)
        series = ind_service.calculate(valid_klines)
        
        strat_service = StrategyService(self.settings.strategy)
        signal = strat_service.evaluate(series)
        
        if signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
            # We assume entry at the exact close of the last candle
            entry_price = Decimal(valid_klines[-1].close)
            signal_time = valid_klines[-1].open_time
            
            risk_service = RiskManagerService(self.settings.risk)
            assessment = risk_service.evaluate(
                symbol=valid_klines[-1].symbol,
                price=entry_price,
                equity=theoretical_equity,
                direction=signal.direction,
                series=series
            )
            
            if assessment.eligible_for_paper_trading and assessment.theoretical_quantity is not None and assessment.stop_loss is not None and assessment.take_profit is not None:
                # Capture!
                obs = ResearchObservation(
                    symbol=valid_klines[-1].symbol,
                    interval=valid_klines[-1].interval,
                    signal_time=signal_time,
                    capture_time=datetime.now(tz=UTC),
                    direction=signal.direction,
                    entry_price=entry_price,
                    stop_loss=assessment.stop_loss,
                    take_profit=assessment.take_profit,
                    theoretical_quantity=assessment.theoretical_quantity,
                    strategy_settings=self.settings.strategy.model_dump(mode="json"),
                    risk_settings=self.settings.risk.model_dump(mode="json"),
                    status=ResearchOutcome.OPEN
                )
                
                # Check for duplicates (same symbol, interval, signal_time)
                observations = self.store.load_observations()
                for existing in observations:
                    if existing.symbol == obs.symbol and existing.interval == obs.interval and existing.signal_time == obs.signal_time:
                        return None # Already captured
                        
                observations.append(obs)
                self.store.save_observations(observations)
                return obs
                
        return None

    def evaluate(self, klines: Sequence[Kline]) -> int:
        """Evaluate OPEN observations using out-of-sample forward klines."""
        if not klines:
            return 0
            
        observations = self.store.load_observations()
        resolved_count = 0
        
        for obs in observations:
            if obs.status != ResearchOutcome.OPEN:
                continue
                
            # Filter forward klines that happen AFTER the signal_time candle
            forward_klines = [k for k in klines if k.open_time > obs.signal_time and k.symbol == obs.symbol and k.interval == obs.interval]
            forward_klines.sort(key=lambda k: k.open_time)
            
            for k in forward_klines:
                hit_stop = False
                hit_target = False
                trigger_price = Decimal("0")
                
                k_low = Decimal(k.low)
                k_high = Decimal(k.high)
                
                if obs.direction == SignalDirection.LONG:
                    if k_low <= obs.stop_loss:
                        hit_stop = True
                        trigger_price = obs.stop_loss
                    if k_high >= obs.take_profit:
                        hit_target = True
                        trigger_price = obs.take_profit if not hit_stop else obs.stop_loss
                else: # SHORT
                    if k_high >= obs.stop_loss:
                        hit_stop = True
                        trigger_price = obs.stop_loss
                    if k_low <= obs.take_profit:
                        hit_target = True
                        trigger_price = obs.take_profit if not hit_stop else obs.stop_loss
                        
                # Resolve outcome: stop loss always wins if both hit in the same candle
                if hit_stop:
                    obs.status = ResearchOutcome.STOP_LOSS
                    obs.resolved_time = k.open_time
                    obs.resolved_price = trigger_price
                    obs.realized_r = Decimal("-1")
                    resolved_count += 1
                    break
                elif hit_target:
                    obs.status = ResearchOutcome.TAKE_PROFIT
                    obs.resolved_time = k.open_time
                    obs.resolved_price = trigger_price
                    # Calculate realized R based on entry, stop, and trigger
                    risk_per_unit = abs(obs.entry_price - obs.stop_loss)
                    if risk_per_unit > Decimal("0"):
                        reward_per_unit = abs(trigger_price - obs.entry_price)
                        obs.realized_r = reward_per_unit / risk_per_unit
                    else:
                        obs.realized_r = Decimal("0")
                    resolved_count += 1
                    break
                    
        if resolved_count > 0:
            self.store.save_observations(observations)
            
        return resolved_count

    def generate_report(self) -> ResearchReport:
        observations = self.store.load_observations()
        
        total = len(observations)
        open_count = sum(1 for o in observations if o.status == ResearchOutcome.OPEN)
        resolved_obs = [o for o in observations if o.status in (ResearchOutcome.TAKE_PROFIT, ResearchOutcome.STOP_LOSS)]
        resolved_count = len(resolved_obs)
        
        win_rate = None
        average_r = None
        expectancy = None
        max_drawdown_r = None
        start_date = None
        end_date = None
        
        if resolved_count > 0:
            wins = sum(1 for o in resolved_obs if o.status == ResearchOutcome.TAKE_PROFIT)
            win_rate = Decimal(wins) / Decimal(resolved_count)
            
            total_r = sum((o.realized_r for o in resolved_obs if o.realized_r is not None), Decimal("0"))
            average_r = total_r / Decimal(resolved_count)
            
            # Expectancy = Average R (since R already factors in loss magnitude of -1)
            expectancy = average_r
            
            # Sort by resolved time to calculate sequence-based R drawdown
            resolved_obs.sort(key=lambda x: x.resolved_time if x.resolved_time else x.signal_time)
            start_date = resolved_obs[0].resolved_time
            end_date = resolved_obs[-1].resolved_time
            
            cumulative_r = Decimal("0")
            peak_r = Decimal("0")
            max_drawdown_r = Decimal("0")
            
            for o in resolved_obs:
                if o.realized_r is not None:
                    cumulative_r += o.realized_r
                    if cumulative_r > peak_r:
                        peak_r = cumulative_r
                    dd = peak_r - cumulative_r
                    if dd > max_drawdown_r:
                        max_drawdown_r = dd
                        
        report = ResearchReport(
            total_observations=total,
            resolved_count=resolved_count,
            open_count=open_count,
            win_rate=win_rate,
            average_r=average_r,
            expectancy=expectancy,
            max_drawdown_r=max_drawdown_r,
            start_date=start_date,
            end_date=end_date
        )
        self.store.save_report(report)
        return report
