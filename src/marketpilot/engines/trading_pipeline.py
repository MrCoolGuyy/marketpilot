"""
MarketPilot Engines - Trading Pipeline.

An application orchestrator for Phase 4 convergence.
It triggers canonical data ingestion, builds causal snapshots,
evaluates strategies, invokes the CausalPipeline, and publishes observations.
"""

import time
from decimal import Decimal
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from marketpilot.core.factory import RuntimeContext

from marketpilot.models.events import (
    CycleStartedEvent,
    CycleFinishedEvent
)

from marketpilot.core.time import MarketObservationClock
from marketpilot.core.enums import AssetType
from marketpilot.strategy.pipeline import CausalPipeline
from marketpilot.strategy.pricing_policy import PricingPolicy
from marketpilot.strategy.validation_policy import ValidationPolicy
from marketpilot.strategy.economics import CausalEconomicsEngine
from marketpilot.models.causal import ExecutableQuoteSnapshot


class TradingPipeline:
    """Orchestrates Phase-4 Causal evaluation and publishes observations."""
    
    def __init__(self, ctx: 'RuntimeContext'):
        self.ctx = ctx
        self.bus = ctx.bus
        self.metrics = ctx.metrics
        
        self.market_data_fetcher = ctx.market_data_fetcher
        self.snapshot_builder = ctx.snapshot_builder
        self.strategy = ctx.strategy
        self.client = ctx.client
        
        # Instantiate the CausalPipeline
        self.causal_pipeline = CausalPipeline(
            pricing=PricingPolicy(),
            validation=ValidationPolicy([]), 
            economics=CausalEconomicsEngine(account_equity=Decimal("1000"))
        )
        
        self._subscribe_all()
        
    def _subscribe_all(self):
        """Wire up the event bus."""
        self.bus.subscribe(CycleStartedEvent, self._on_cycle_started)
        
    async def _on_cycle_started(self, event: CycleStartedEvent):
        start = time.time()
        logger.info(f"Cycle {event.ctx.cycle_id}: Orchestrating Phase-4 Causal Pipeline...")
        
        try:
            # 1. Fetch scan candidates
            limit = self.ctx.settings.scanner.max_results
            quote_coin = self.ctx.settings.scanner.quote_coin
            min_turnover = self.ctx.settings.scanner.min_turnover_24h
            
            raw_candidates = await self.market_data_fetcher.fetch_scan_candidates(
                quote_coin=quote_coin,
                min_turnover_24h=min_turnover,
                limit=limit
            )
            
            # 2. Build ClosedInstrumentSnapshots & Evaluate Strategy
            intents = []
            valid_snapshots = []
            raw_snaps = []
            
            for raw in raw_candidates:
                clock = MarketObservationClock(
                    observed_at=raw.timestamp,
                    time_source="BYBIT_SERVER_TIME",
                    provenance="MAINNET_REST"
                )
                raw_snaps.append(self.snapshot_builder.build(raw))
                
            scanner_result = self.ctx.scanner.evaluate(raw_snaps)
            top_symbols = {s.symbol for s in scanner_result.top_candidates}
            
            for raw in raw_candidates:
                if raw.symbol not in top_symbols:
                    continue
                    
                clock = MarketObservationClock(
                    observed_at=raw.timestamp,
                    time_source="BYBIT_SERVER_TIME",
                    provenance="MAINNET_REST"
                )
                result = self.snapshot_builder.build_causal(raw, clock)
                if result.snapshot:
                    snapshot = result.snapshot
                    valid_snapshots.append(snapshot)
                    
                    from marketpilot.models.indicators import IndicatorSeries
                    from marketpilot.models.regime import MarketRegime
                    from marketpilot.core.enums import Interval
                    
                    series = self.ctx.indicator.calculate(raw.klines)
                    regime = MarketRegime.RANGING
                    
                    strategy_intents, _ = self.strategy.evaluate(series, regime, snapshot, event.ctx.decision_id)
                    intents.extend(strategy_intents)
            
            # 3. Genuinely acquire ExecutableQuoteSnapshots AFTER intents are finalized
            quotes = {}
            if intents:
                logger.info("Fetching real-time executable quotes for generated intents...")
                for intent in intents:
                    snap = next((s for s in valid_snapshots if s.snapshot_id == intent.provenance_snapshot_id), None)
                    if snap:
                        live_tickers = await self.client.get_tickers(snap.symbol, asset_type=AssetType.LINEAR)
                        if live_tickers:
                            bid = Decimal(live_tickers[0].bid_price)
                            ask = Decimal(live_tickers[0].ask_price)
                            quote = ExecutableQuoteSnapshot(
                                quote_id=f"quote_{int(time.time())}",
                                symbol=snap.symbol,
                                environment=snap.environment,
                                quote_timestamp=time.time(), # Genuinely causal
                                bid=bid,
                                ask=ask
                            )
                            quotes[intent.identity.strategy_id] = quote

            # 4. Process through CausalPipeline
            logger.info(f"Cycle {event.ctx.cycle_id}: CausalPipeline processing {len(intents)} intents.")
            batch_result = self.causal_pipeline.process_signals(
                intents=intents,
                quotes=quotes,
                regime_model="trend_smoke",
                regime_state="BULL",
                market_scope="ALL"
            )
            
            # 5. Stop. (No Phase-5 execution)
            logger.info(f"Cycle {event.ctx.cycle_id}: Phase-4 boundary reached. Candidates: {len(batch_result.candidates)}")
            
            # 6. Publish Observations to Dashboard Read Store via durable FileProjectionRepository
            from marketpilot.dashboard.projections import FileProjectionRepository
            from marketpilot.dashboard.store import DashboardProjection
            repo = FileProjectionRepository()
            intelligence = [DashboardProjection.project_market_intelligence(s) for s in valid_snapshots]
            evidence = []
            
            for rank, candidate in enumerate(batch_result.candidates, 1):
                evidence.append(DashboardProjection.project_candidate(candidate, rank))
                
            from marketpilot.models.causal import CandidateRejectedObserved
            for obs in batch_result.observations:
                if isinstance(obs, CandidateRejectedObserved):
                    evidence.append(DashboardProjection.project_rejection(obs))
                    
            from marketpilot.dashboard.models import ProjectionMetadata
            
            # Determine outcome
            if not intents:
                outcome = "NO_SIGNAL"
                reason = "Strategy evaluated and returned no signal (ABSTAIN or absent features)"
            elif not batch_result.candidates:
                outcome = "SIGNALS_GENERATED_NO_ELIGIBLE_CANDIDATE"
                reason = "Intents generated but failed pricing, evidence, or economic bounds"
            else:
                outcome = "CANDIDATES_GENERATED"
                reason = "Eligible candidates successfully generated"
            
            priced_count = len(batch_result.candidates)
            rejected_before_pricing_count = 0
            rejected_at_evidence_count = 0
            rejected_at_economics_count = 0
            
            for obs in batch_result.observations:
                if isinstance(obs, CandidateRejectedObserved):
                    if obs.pricing_status.value != "PRICED":
                        rejected_before_pricing_count += 1
                    else:
                        priced_count += 1
                        if obs.evidence_status.value in ("NO_EVIDENCE", "INSUFFICIENT", "STALE"):
                            rejected_at_evidence_count += 1
                        else:
                            rejected_at_economics_count += 1
                            
            meta = ProjectionMetadata(
                projection_version=1,
                evaluation_id=event.ctx.cycle_id,
                daemon_instance_id=getattr(event.ctx, "daemon_instance_id", "unknown"),
                generated_at=time.time(),
                evaluation_as_of=event.ctx.market_time.timestamp(),
                cycle_outcome=outcome,
                cycle_reason=reason,
                intents_count=len(intents),
                priced_count=priced_count,
                evidence_evaluated_count=priced_count, # Since evidence evaluation happens for all priced candidates
                final_candidates_count=len(batch_result.candidates),
                rejected_before_pricing_count=rejected_before_pricing_count,
                rejected_at_evidence_count=rejected_at_evidence_count,
                rejected_at_economics_count=rejected_at_economics_count,
                candidates_count=len(batch_result.candidates),
                evaluation_cadence_seconds=self.ctx.settings.daemon.evaluation_interval_seconds if hasattr(self.ctx.settings, 'daemon') else 60
            )
                    
            repo.publish_daemon_evaluation(intelligence, evidence, metadata=meta)
            
        except Exception as e:
            logger.error(f"Cycle {event.ctx.cycle_id}: TradingPipeline Phase-4 orchestration failed: {e}")
        
        self.metrics.record_latency("trading_pipeline", (time.time() - start) * 1000)
        await self.bus.publish(CycleFinishedEvent(ctx=event.ctx))
