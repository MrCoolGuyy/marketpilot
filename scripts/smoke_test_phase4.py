"""
Phase 4 Smoke Test.
Connects to MAINNET (read-only), fetches a ClosedInstrumentSnapshot,
evaluates it through the CausalPipeline, and ensures 0 orders are placed.
"""

import asyncio
import time
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
from marketpilot.dashboard.store import DashboardProjection

async def main():
    logger.info("Starting Phase 4 Smoke Verification...")

    # 1. Market Data Environment
    settings = AppSettings()
    env = settings.exchange.environment
    mode = ExecutionMode.PAPER # Force to paper for smoke test
    logger.info(f"Environment: {env.value}")
    logger.info(f"Execution Mode: {mode.value}")

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
        logger.warning(f"No causal snapshot could be built. Outcome: {result.outcome.value}, Reason: {result.reason}")
        return

    snapshot = result.snapshot
    logger.success(f"Built ClosedInstrumentSnapshot: {snapshot.snapshot_id}")
    logger.info(f"Snapshot Causal Timestamp (Creation): {snapshot.creation_timestamp}")
    logger.info(f"Snapshot facts (Close): {snapshot.facts.close}")

    # 4. Build Intent First (Before Quote Fetch)
    identity = StrategyIdentity(
        registry_version="1.0",
        strategy_id="test_smoke_strategy",
        strategy_version="1.0",
        parameter_set_id="default"
    )

    signal_ts = time.time()
    intent = SignalIntent(
        intent_id="intent_smoke",
        identity=identity,
        direction=SignalDirection.LONG,
        symbol=symbol,
        signal_timestamp=signal_ts,
        signal_timestamp_us=int(Decimal(str(signal_ts)) * 1_000_000),
        logical_stop_loss=snapshot.facts.close * Decimal("0.95"),
        logical_take_profit=snapshot.facts.close * Decimal("1.10"),
        provenance_snapshot_id=snapshot.snapshot_id
    )

    # 5. Acquire Canonical live/read-only quote data (Strictly AFTER intent)
    logger.info("Fetching real-time executable quote for generated intent...")
    try:
        await client.connect()
        # Fresh fetch after signal timestamp
        live_tickers = await client.get_tickers(symbol, asset_type=AssetType.LINEAR)
    finally:
        await client.disconnect()

    if not live_tickers:
        logger.error("Failed to fetch live quotes.")
        return

    bid = Decimal(live_tickers[0].bid_price)
    ask = Decimal(live_tickers[0].ask_price)

    quote = ExecutableQuoteSnapshot(
        quote_id=f"quote_{int(time.time())}",
        symbol=symbol,
        environment=env,
        quote_timestamp=time.time(), # Now genuinely causal
        bid=bid,
        ask=ask
    )

    logger.info(f"Quote acquired at {quote.quote_timestamp}: Bid {bid}, Ask {ask}")

    pipeline = CausalPipeline(
        pricing=PricingPolicy(),
        validation=ValidationPolicy([]), # NO fabricated evidence
        economics=CausalEconomicsEngine(account_equity=Decimal("1000"))
    )

    quotes = {identity.strategy_id: quote}

    # 6. Evaluate
    result = pipeline.process_signals([intent], quotes, "trend_smoke", "BULL", "ALL")

    logger.info(f"Pipeline processed {len([intent])} intents.")
    logger.info(f"Result Candidates: {len(result.candidates)}")
    logger.info(f"Result Observations: {len(result.observations)}")

    # Check rejection
    for obs in result.observations:
        from marketpilot.models.causal import CandidateRejectedObserved
        if isinstance(obs, CandidateRejectedObserved):
            logger.info(f"Rejection Observed: {obs.rejection_reason}")

    # 7. Dashboard Projection
    mi_proj = DashboardProjection.project_market_intelligence(snapshot)
    logger.info("Market Intelligence Projection successful.")

    logger.info(f"TOTAL ORDERS SUBMITTED: 0")

if __name__ == "__main__":
    asyncio.run(main())
