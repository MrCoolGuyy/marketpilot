"""MarketPilot Autopilot — Candidate Selector Service."""

import asyncio
from decimal import Decimal

from loguru import logger

from marketpilot.config.settings import AppSettings
from marketpilot.core.enums import Interval
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.autopilot import CandidateDecision, AutopilotStatus
from marketpilot.models.strategy import SignalDirection
from marketpilot.risk.service import RiskManagerService
from marketpilot.scanner.service import ScannerService
from marketpilot.strategy.service import StrategyService
from marketpilot.exchange.bybit_client import BybitClient


class CandidateSelectorService:
    """Scans and ranks execution candidates."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    async def select_best_candidate(self, equity: Decimal) -> CandidateDecision | None:
        """Scan all eligible symbols and return the strongest candidate."""
        
        client = BybitClient(self.settings.demo)
        # Verify connectivity and get tickers for turnover ranking
        try:
            await client.connect()
            tickers = await client.get_tickers()
            ticker_map = {t.symbol: t for t in tickers}
        except Exception as e:
            logger.error(f"Failed to fetch market data: {e}")
            return None
        finally:
            await client.disconnect()

        # Step 1: Scan
        scanner = ScannerService(BybitClient(self.settings.scanner), self.settings.scanner)
        scan_results = await scanner.scan(Interval.H1)
        
        # Step 2 & 3: Evaluate Indicators & Strategy
        ind_service = IndicatorService(self.settings.indicators)
        strat_service = StrategyService(self.settings.strategy)
        risk_service = RiskManagerService(self.settings.risk)
        
        candidates: list[CandidateDecision] = []
        
        for result in scan_results:
            if result.error or not result.klines:
                continue
                
            closed_klines = [k for k in result.klines if k.is_closed]
            if not closed_klines:
                continue
                
            series = ind_service.calculate(closed_klines)
            signal = strat_service.evaluate(series)
            
            # Require perfectly strong signal
            if signal.score < Decimal("100") or signal.direction == SignalDirection.NEUTRAL:
                continue
                
            # Get live price and ATR for risk
            ticker = ticker_map.get(result.symbol)
            if not ticker:
                continue
                
            entry_price = ticker.ask_price if signal.direction == SignalDirection.LONG else ticker.bid_price
            if not entry_price or entry_price <= 0:
                continue
                
            atr_series = [p for p in series if p.atr is not None]
            if not atr_series:
                continue
            atr = atr_series[-1].atr
                
            assessment = risk_service.assess(
                signal=signal,
                entry_price=entry_price,
                atr=atr,
                account_equity=equity
            )
            
            if not assessment.eligible_for_paper_trading or assessment.theoretical_quantity is None:
                continue
                
            candidates.append(
                CandidateDecision(
                    symbol=result.symbol,
                    interval=Interval.H1,
                    candle_time=closed_klines[-1].open_time,
                    direction=signal.direction,
                    score=signal.score,
                    turnover=ticker.turnover_24h,
                    entry_estimate=entry_price,
                    quantity=assessment.theoretical_quantity,
                    stop_loss=assessment.stop_loss,
                    take_profit=assessment.take_profit,
                    status=AutopilotStatus.SUGGEST_ONLY
                )
            )
            
        if not candidates:
            return None
            
        # Step 4: Deterministic Ranking
        # 1. Score (descending)
        # 2. Turnover (descending)
        # 3. Symbol (ascending)
        candidates.sort(key=lambda c: (-c.score, -c.turnover, c.symbol))
        
        return candidates[0]
