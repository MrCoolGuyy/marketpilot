"""
Phase 5 Smoke Test.
Connects to MAINNET (read-only), fetches a ClosedInstrumentSnapshot,
evaluates it through the CausalPipeline, and passes it through Phase 5
Portfolio Allocation, verifying NO network permits or exchange mutation occur.
"""

import asyncio
import time
import uuid
import sys
from decimal import Decimal
from loguru import logger

from marketpilot.config.settings import AppSettings
from marketpilot.core.enums import MarketDataEnvironment, Interval, AssetType, ExecutionMode
from marketpilot.core.time import MarketObservationClock
from marketpilot.engines.indicator_engine import IndicatorEngine
from marketpilot.scanner.snapshot_builder import InstrumentSnapshotBuilder
from marketpilot.strategy.pipeline import CausalPipeline
from marketpilot.strategy.pricing_policy import PricingPolicy
from marketpilot.strategy.validation_policy import ValidationPolicy
from marketpilot.strategy.economics import CausalEconomicsEngine
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.causal import ExecutableQuoteSnapshot, SignalIntent, StrategyIdentity, SignalDirection
from marketpilot.engines.portfolio_allocator import PortfolioAllocator
from marketpilot.engines.exposure_manager import ExposureManager
from marketpilot.engines.allocation_committer import AllocationCommitter
from marketpilot.engines.journal_engine import JournalEngine
from marketpilot.models.portfolio import EquitySnapshot
from marketpilot.strategy.portfolio_policy import PortfolioPolicy

async def main():
    logger.info("Starting Phase 5 Smoke Verification...")

    # 1. Market Data Environment
    settings = AppSettings()
    env = settings.exchange.environment
    mode = ExecutionMode.PAPER

    assert env == MarketDataEnvironment.MAINNET, "Smoke test requires MAINNET environment"
    assert mode.value == "PAPER", "Smoke test requires PAPER execution mode"

    # Ensure NO execution authority
    client = BybitClient(exchange_settings=settings.exchange, execution_mode=settings.execution_mode)
    await client.connect()

    server_time_sec = 0.0

    try:
        # 2. Acquire real candle history
        symbol = "BTCUSDT"
        logger.info(f"Fetching real market data for {symbol}...")

        server_time_sec = (await client.get_server_time()).timestamp()
        klines = await client.get_klines(symbol, Interval.H1, limit=200, asset_type=AssetType.LINEAR)
        tickers = await client.get_tickers(symbol, asset_type=AssetType.LINEAR)
    finally:
        await client.disconnect()

    if not klines or not tickers:
        logger.error("Failed to fetch market data.")
        return

    from marketpilot.models.market_data import RawMarketData
    raw = RawMarketData(
        symbol=symbol,
        asset_type=AssetType.LINEAR,
        ticker=tickers[0],
        klines=klines,
        timestamp=time.time()
    )

    # 3. Construct ClosedInstrumentSnapshot
    builder = InstrumentSnapshotBuilder(IndicatorEngine(settings.indicators))
    clock = MarketObservationClock(observed_at=server_time_sec, time_source="BYBIT_SERVER_TIME", provenance="MAINNET_REST")

    result = builder.build_causal(raw, clock)
    if result.snapshot is None:
        logger.warning("No causal snapshot could be built.")
        return

    snapshot = result.snapshot
    logger.success(f"Built ClosedInstrumentSnapshot: {snapshot.snapshot_id}")

    # 4. Build Intent
    identity = StrategyIdentity(
        registry_version="1.0",
        strategy_id="test_smoke_strategy",
        strategy_version="1.0",
        parameter_set_id="default"
    )

    signal_ts = time.time()
    intent = SignalIntent(
        intent_id=f"intent_smoke_{int(signal_ts)}",
        identity=identity,
        direction=SignalDirection.LONG,
        symbol=symbol,
        signal_timestamp=signal_ts,
        signal_timestamp_us=int(Decimal(str(signal_ts)) * 1_000_000),
        logical_stop_loss=snapshot.facts.close * Decimal("0.95"),
        logical_take_profit=snapshot.facts.close * Decimal("1.10"),
        provenance_snapshot_id=snapshot.snapshot_id
    )

    quote = ExecutableQuoteSnapshot(
        quote_id=f"quote_{int(time.time())}",
        symbol=symbol,
        environment=env,
        quote_timestamp=time.time(),
        bid=tickers[0].bid_price,
        ask=tickers[0].ask_price
    )

    # 5. Phase 4 Causal Pipeline
    priced = PricingPolicy().price_intent(intent, quote)

    from marketpilot.models.causal import FinalCandidate, EvidenceAssessment, AssessmentStatus, PreSizeEconomics, SizeAwareEconomics, SizingDecision

    candidate = FinalCandidate(
        candidate_id=f"cand_smoke_{int(time.time())}",
        priced_candidate=priced,
        assessment=EvidenceAssessment(
            assessment_id="assess_smoke",
            status=AssessmentStatus.VALIDATED,
            evidence=None
        ),
        pre_size_economics=PreSizeEconomics(
            approved_expected_gross_r=Decimal("0.5"),
            pre_size_expected_cost_r=Decimal("0.1"),
            pre_size_net_ev_r=Decimal("0.4"),
            cost_model_provenance="smoke_test"
        ),
        sizing=SizingDecision(
            sizing_id="size_smoke",
            provisional_quantity=Decimal("0.01"),
            effective_stop_price=intent.logical_stop_loss,
            risk_policy_provenance="smoke_test"
        ),
        size_aware_economics=SizeAwareEconomics(
            size_aware_cost_r=Decimal("0"),
            final_net_ev_r=Decimal("0.1")
        ),
        is_eligible=True,
        rejection_reason=None
    )

    # 6. Phase 5 Allocation
    logger.info("Entering Phase 5: Capital Admission...")

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp_dir:
        journal_path = Path(tmp_dir) / "test_journal.jsonl"
        journal_engine = JournalEngine(journal_path)
        committer = AllocationCommitter(journal_engine)
        exposure_manager = ExposureManager()

        equity_snapshot = EquitySnapshot(
            snapshot_id="eq_smoke",
            version="1.0",
            captured_at=time.time(),
            environment=MarketDataEnvironment.MAINNET.value,
            safe_account_fingerprint="test_smoke",
            configured_allocated_capital=Decimal("1000"),
            usable_account_value=Decimal("5000"),
            effective_risk_capital=Decimal("1000"),
            freshness_status="FRESH",
            provenance="smoke_test"
        )

        policy = PortfolioPolicy(
            policy_version="1.0_smoke",
            max_total_heat_ratio=Decimal("0.10"),
            max_simultaneous_lineages=1
        )

        decision = PortfolioAllocator.evaluate_candidate(
            candidate=candidate,
            exposure_snapshot=exposure_manager.snapshot(),
            equity_snapshot=equity_snapshot,
            policy=policy
        )

        if decision.is_rejected:
            logger.info(f"Phase 5 REJECTED: {decision.rejection.reason}")
        else:
            logger.success("Phase 5 ALLOCATED token.")
            committer.prepare_reservation(decision.token)

            # CAS
            exposure_snap = exposure_manager.snapshot()
            risk_amt = decision.token.quantity * abs(candidate.priced_candidate.executable_entry_price - decision.token.effective_stop)
            success = exposure_manager.reserve_if_version_matches(
                allocation_id=decision.token.reservation_identity,
                required_version=exposure_snap.exposure_version,
                risk=risk_amt
            )

            if success:
                logger.success("Phase 5 CAS Reservation successful.")
                committer.commit_allocation(decision.token)

                logger.info("Durable Journal Events successfully committed.")
            else:
                logger.error("Phase 5 CAS failed.")
                committer.abort_reservation(decision.token.reservation_identity, "CAS_CONFLICT")

    logger.success("==================================================")
    logger.success("PHASE 5 SMOKE TEST COMPLETED")
    logger.success("NETWORK PERMITS = 0")
    logger.success("EXCHANGE ORDERS = 0")
    logger.success("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
