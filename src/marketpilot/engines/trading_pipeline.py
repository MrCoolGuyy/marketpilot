"""
MarketPilot Engines - Trading Pipeline.

An application orchestrator for Phase 4 convergence.
It triggers canonical data ingestion, builds causal snapshots,
evaluates strategies, invokes the CausalPipeline, and publishes observations.
"""

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Final
from loguru import logger

if TYPE_CHECKING:
    from marketpilot.core.factory import RuntimeContext

from marketpilot.models.events import CycleStartedEvent, CycleFinishedEvent

from marketpilot.core.time import MarketObservationClock
from marketpilot.core.enums import AssetType
from marketpilot.strategy.pipeline import CausalPipeline
from marketpilot.strategy.pricing_policy import PricingPolicy
from marketpilot.strategy.validation_policy import ValidationPolicy
from marketpilot.strategy.economics import CausalEconomicsEngine
from marketpilot.strategy.portfolio_policy import PortfolioPolicy
from marketpilot.engines.portfolio_allocator import PortfolioAllocator
from marketpilot.engines.allocation_committer import AllocationCommitter
from marketpilot.models.portfolio import EquitySnapshot
from marketpilot.models.causal import ExecutableQuoteSnapshot
from marketpilot.notifications.policy import NotificationPolicy

MAX_CAS_RETRIES: Final = 3
"""Deterministic bounded limit for optimistic concurrency exposure snapshot collisions during capital admission."""


class TradingPipeline:
    """Orchestrates Phase-4 Causal evaluation and publishes observations."""

    def __init__(self, ctx: "RuntimeContext"):
        self.ctx = ctx
        self.bus = ctx.bus
        self.metrics = ctx.metrics

        self.market_data_fetcher = ctx.market_data_fetcher
        self.snapshot_builder = ctx.snapshot_builder
        self.strategy = ctx.strategy
        self.client = ctx.client

        self.notification_policy = NotificationPolicy(ctx.notifier)

        # Instantiate the CausalPipeline
        self.causal_pipeline = CausalPipeline(
            pricing=PricingPolicy(),
            validation=ValidationPolicy([]),
            economics=CausalEconomicsEngine(),
        )
        self.portfolio_policy = PortfolioPolicy(
            policy_version="V1-PHASE5",
            allocated_capital=self.ctx.settings.portfolio.allocated_capital,
            minimum_unallocated_buffer=self.ctx.settings.portfolio.minimum_unallocated_buffer,
            max_total_heat_ratio=self.ctx.settings.portfolio.max_total_heat_ratio,
            max_simultaneous_lineages=self.ctx.settings.portfolio.max_simultaneous_lineages,
        )
        self.allocation_committer = AllocationCommitter()

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
                quote_coin=quote_coin, min_turnover_24h=min_turnover, limit=limit
            )

            # 2. Build ClosedInstrumentSnapshots & Evaluate Strategy
            intents = []
            valid_snapshots = []
            raw_snaps = []

            for raw in raw_candidates:
                clock = MarketObservationClock(
                    observed_at=raw.timestamp,
                    time_source="BYBIT_SERVER_TIME",
                    provenance="MAINNET_REST",
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
                    provenance="MAINNET_REST",
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

                    strategy_intents, _ = self.strategy.evaluate(
                        series, regime, snapshot, event.ctx.decision_id
                    )
                    intents.extend(strategy_intents)

            # 3. Genuinely acquire ExecutableQuoteSnapshots AFTER intents are finalized
            quotes = {}
            if intents:
                logger.info("Fetching real-time executable quotes for generated intents...")
                for intent in intents:
                    snap = next(
                        (
                            s
                            for s in valid_snapshots
                            if s.snapshot_id == intent.provenance_snapshot_id
                        ),
                        None,
                    )
                    if snap:
                        live_tickers = await self.client.get_tickers(
                            snap.symbol, asset_type=AssetType.LINEAR
                        )
                        if live_tickers:
                            bid = Decimal(live_tickers[0].bid_price)
                            ask = Decimal(live_tickers[0].ask_price)
                            quote = ExecutableQuoteSnapshot(
                                quote_id=f"quote_{int(time.time())}",
                                symbol=snap.symbol,
                                environment=snap.environment,
                                quote_timestamp=time.time(),  # Genuinely causal
                                bid=bid,
                                ask=ask,
                            )
                            quotes[intent.identity.strategy_id] = quote

            # 3.5 Fetch Authoritative Equity for Sizing (Mandate requires effective_risk_capital)
            allocated_cap = self.ctx.settings.portfolio.allocated_capital
            try:
                bal_resp = await self.client.get_wallet_balance(account_type="UNIFIED")
                list_data = bal_resp.get("result", {}).get("list", [])
                raw_eq = "0"
                raw_avail = "0"
                if list_data:
                    coins = list_data[0].get("coin", [])
                    for coin_data in coins:
                        if coin_data.get("coin") == "USDT":
                            raw_eq = coin_data.get("equity", "0")
                            raw_avail = coin_data.get("availableToWithdraw", "0")
                            break
                    if raw_eq == "0" and raw_avail == "0":
                        raw_eq = list_data[0].get("totalEquity", "0")
                        raw_avail = list_data[0].get("totalAvailableBalance", "0")
            except Exception as e:
                logger.warning(f"Failed to fetch equity. Failing closed: {e}")
                raw_eq = "0"
                raw_avail = "0"

            usable_account_value = Decimal(str(raw_avail))
            effective_risk_capital = self.portfolio_policy.calculate_effective_risk_capital(usable_account_value)
            if effective_risk_capital == Decimal("0") and self.portfolio_policy.allocated_capital is None:
                logger.warning("Phase 5 disabled: allocated_capital is missing. Failing closed.")

            equity_snapshot = EquitySnapshot(
                snapshot_id=f"eq_{int(time.time() * 1000)}",
                version="1.0",
                captured_at=time.time(),
                environment=self.ctx.settings.execution_mode.value,
                safe_account_fingerprint="bybit_uta",
                configured_allocated_capital=allocated_cap,
                usable_account_value=usable_account_value,
                effective_risk_capital=effective_risk_capital,
                freshness_status="FRESH",
                provenance="bybit_get_wallet_balance",
            )

            # 4. Process through CausalPipeline
            logger.info(
                f"Cycle {event.ctx.cycle_id}: CausalPipeline processing {len(intents)} intents."
            )
            batch_result = self.causal_pipeline.process_signals(
                intents=intents,
                quotes=quotes,
                regime_model="trend_smoke",
                regime_state="BULL",
                market_scope="ALL",
                effective_risk_capital=effective_risk_capital,
                risk_fraction=self.ctx.settings.risk.risk_per_trade_fraction,
                max_risk_fraction=self.ctx.settings.risk.max_risk_per_trade_fraction,
            )

            # 5. Stop. (No Phase-5 execution)
            logger.info(
                f"Cycle {event.ctx.cycle_id}: Phase-4 boundary reached. Candidates: {len(batch_result.candidates)}"
            )

            # 6. Publish Observations to Dashboard Read Store via durable FileProjectionRepository
            from marketpilot.dashboard.projections import FileProjectionRepository
            from marketpilot.dashboard.store import DashboardProjection

            repo = FileProjectionRepository()
            intelligence = [
                DashboardProjection.project_market_intelligence(s) for s in valid_snapshots
            ]
            evidence = []

            for rank, candidate in enumerate(batch_result.candidates, 1):
                evidence.append(DashboardProjection.project_candidate(candidate, rank))

            from marketpilot.models.causal import CandidateRejectedObserved

            for obs in batch_result.observations:
                if isinstance(obs, CandidateRejectedObserved):
                    evidence.append(DashboardProjection.project_rejection(obs))
                    if obs.pricing_status.value == "PRICED" and obs.evidence_status.value in (
                        "NO_EVIDENCE",
                        "INSUFFICIENT",
                        "STALE",
                    ):
                        import asyncio

                        asyncio.create_task(self.notification_policy.notify_evidence_rejection(obs))

            # -----------------------------------------------------------------
            # PHASE 5: PORTFOLIO ALLOCATION & DURABLE CAPITAL ADMISSION
            # -----------------------------------------------------------------

            admitted_candidates = []

            if batch_result.candidates:
                portfolio_rejections_heat = 0
                portfolio_rejections_lineage = 0

                # 2. Iterate deterministically over eligible Phase 4 candidates
                for candidate in batch_result.candidates:
                    # Retry loop for CAS safety
                    for _ in range(MAX_CAS_RETRIES):
                        exposure_snapshot = self.ctx.exposure.snapshot()

                        decision = PortfolioAllocator.evaluate_candidate(
                            candidate=candidate,
                            exposure_snapshot=exposure_snapshot,
                            equity_snapshot=equity_snapshot,
                            policy=self.portfolio_policy,
                        )

                        if decision.is_rejected:
                            logger.info(
                                f"Phase 5 REJECTED {candidate.candidate_id}: {decision.rejection.reason}"
                            )
                            if decision.rejection.rejection_code == "HEAT_EXCEEDED":
                                portfolio_rejections_heat += 1
                            elif decision.rejection.rejection_code in (
                                "LINEAGE_EXISTS",
                                "LINEAGE_LIMIT_EXCEEDED",
                            ):
                                portfolio_rejections_lineage += 1

                            import asyncio

                            asyncio.create_task(
                                self.notification_policy.notify_portfolio_rejection(
                                    candidate=candidate,
                                    decision=decision,
                                    exposure=exposure_snapshot,
                                )
                            )
                            # Could emit a PortfolioRejectionObserved here
                            break

                        # 1. Phase 5 Durable Preparation
                        self.allocation_committer.prepare_reservation(decision.token)

                        # 2. Try to reserve capital atomically (CAS)
                        success = self.ctx.exposure.reserve_if_version_matches(
                            allocation_id=decision.token.reservation_identity,
                            required_version=exposure_snapshot.exposure_version,
                            risk=decision.token.quantity
                            * abs(
                                candidate.priced_candidate.executable_entry_price
                                - decision.token.effective_stop
                            ),
                        )

                        if success:
                            # 3. Phase 5 Durable Commit
                            risk_amt = decision.token.quantity * abs(
                                candidate.priced_candidate.executable_entry_price
                                - decision.token.effective_stop
                            )
                            logger.success(
                                f"Phase 5 ADMITTED {candidate.candidate_id}. Reserved risk {risk_amt}."
                            )

                            admitted_token = self.allocation_committer.commit_allocation(
                                decision.token
                            )
                            logger.info(
                                f"AllocationCommitter durably admitted token: {admitted_token.reservation_identity}"
                            )

                            admitted_candidates.append(candidate)

                            import asyncio

                            asyncio.create_task(
                                self.notification_policy.notify_phase5_admission(
                                    candidate=candidate,
                                    decision=decision,
                                    exposure=exposure_snapshot,
                                    equity=equity_snapshot,
                                )
                            )
                            asyncio.create_task(
                                self.notification_policy.notify_reservation_committed(
                                    admitted_token
                                )
                            )

                            if self.ctx.settings.execution_mode.value == "PAPER":
                                from marketpilot.models.execution import ExecutionQuoteSnapshot
                                quote_snap = ExecutionQuoteSnapshot(
                                    quote_id=candidate.priced_candidate.quote.quote_id,
                                    symbol=candidate.priced_candidate.quote.symbol,
                                    bid=candidate.priced_candidate.quote.bid,
                                    ask=candidate.priced_candidate.quote.ask,
                                    source_market_timestamp=candidate.priced_candidate.quote.quote_timestamp, # Or datetime from float
                                    received_at=candidate.priced_candidate.quote.quote_timestamp, # wait ExecutionQuoteSnapshot uses datetime
                                    source=candidate.priced_candidate.quote.environment
                                )
                                # Need to convert floats to datetime.
                                from datetime import datetime, UTC
                                quote_snap = ExecutionQuoteSnapshot(
                                    quote_id=candidate.priced_candidate.quote.quote_id,
                                    symbol=candidate.priced_candidate.quote.symbol,
                                    bid=candidate.priced_candidate.quote.bid,
                                    ask=candidate.priced_candidate.quote.ask,
                                    source_market_timestamp=datetime.fromtimestamp(candidate.priced_candidate.quote.quote_timestamp, UTC),
                                    received_at=datetime.fromtimestamp(candidate.priced_candidate.quote.quote_timestamp, UTC),
                                    source="BYBIT"
                                )
                                self.ctx.execution_coordinator.process_allocation(token=admitted_token, quote=quote_snap, take_profit=candidate.priced_candidate.intent.take_profit, environment="PAPER")

                            # Stop after successful admission to evaluate next candidate with fresh exposure
                            break
                        else:
                            # 3. Phase 5 Durable Abort
                            self.allocation_committer.abort_reservation(
                                decision.token.reservation_identity, "CAS_CONFLICT"
                            )
                            logger.warning(
                                f"CAS conflict during Phase 5 reservation for {candidate.candidate_id}. Retrying..."
                            )

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
                evidence_evaluated_count=priced_count,  # Since evidence evaluation happens for all priced candidates
                final_candidates_count=len(batch_result.candidates),
                rejected_before_pricing_count=rejected_before_pricing_count,
                rejected_at_evidence_count=rejected_at_evidence_count,
                rejected_at_economics_count=rejected_at_economics_count,
                candidates_count=len(batch_result.candidates),
                evaluation_cadence_seconds=self.ctx.settings.daemon.evaluation_interval_seconds
                if hasattr(self.ctx.settings, "daemon")
                else 60,
            )

            repo.publish_daemon_evaluation(intelligence, evidence, metadata=meta)

            # Publish Cycle Summary via Telegram
            exp_snap = locals().get("exposure_snapshot")
            eq_snap = locals().get("equity_snapshot")
            top_cand = batch_result.candidates[0] if batch_result.candidates else None

            import asyncio

            asyncio.create_task(
                self.notification_policy.notify_cycle_summary(
                    cycle_id=event.ctx.cycle_id,
                    time_str=str(event.ctx.market_time),
                    mode=self.ctx.settings.execution_mode.value,
                    env="MAINNET"
                    if self.ctx.settings.execution_mode.value == "PAPER"
                    else "UNKNOWN",
                    outcome=outcome,
                    universe_size=len(valid_snapshots),
                    market_qualified=len(valid_snapshots),
                    signals=len(intents),
                    priced=priced_count,
                    evidence_evaluated=priced_count,
                    eligible=len(batch_result.candidates),
                    admitted=len(admitted_candidates),
                    rejected=len(batch_result.candidates)
                    - len(admitted_candidates)
                    + rejected_before_pricing_count
                    + rejected_at_evidence_count
                    + rejected_at_economics_count,
                    rejections_evidence=rejected_at_evidence_count,
                    rejections_economics=rejected_at_economics_count,
                    rejections_heat=locals().get("portfolio_rejections_heat", 0),
                    rejections_lineage=locals().get("portfolio_rejections_lineage", 0),
                    current_heat=str(exp_snap.total_risk_amount) if exp_snap else "N/A",
                    heat_limit=str(exp_snap.policy_limit_risk_amount) if exp_snap else "N/A",
                    effective_capital=str(eq_snap.effective_risk_capital) if eq_snap else "N/A",
                    active_lineages=len(exp_snap.active_position_ids) if exp_snap else 0,
                    reservations=len(exp_snap.reserved_allocation_ids) if exp_snap else 0,
                    top_candidate=top_cand,
                    top_decision=None,
                )
            )

        except Exception as e:
            logger.exception(
                f"Cycle {event.ctx.cycle_id}: TradingPipeline Phase-4 orchestration failed: {e!r}"
            )

        self.metrics.record_latency("trading_pipeline", (time.time() - start) * 1000)
        await self.bus.publish(CycleFinishedEvent(ctx=event.ctx))
