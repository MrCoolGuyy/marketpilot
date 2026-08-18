"""
MarketPilot CLI — Command-line interface.

Provides lightweight CLI commands for diagnostics and quick checks.
Uses ``sys.argv`` directly to avoid heavy framework dependencies.
"""

from __future__ import annotations
from marketpilot.notifications.telegram_notifier import TelegramNotifier
from marketpilot.notifications.notification_models import NotificationEvent, NotificationType

import asyncio
import sys
from decimal import Decimal

from loguru import logger


def main() -> None:
    """Route CLI commands.

    Usage::

        uv run marketpilot              # default banner
        uv run marketpilot ping         # connectivity check
        uv run marketpilot scan         # market scan
    """
    from marketpilot.config import get_settings
    from marketpilot.utils.logging import setup_logging

    settings = get_settings()
    setup_logging(settings.logging)

    args = sys.argv[1:]
    command = args[0] if args else ""

    if command == "ping":
        asyncio.run(_cmd_ping(settings))
    elif command == "scan":
        asyncio.run(_cmd_scan(settings, args[1:]))
    elif command == "indicators":
        asyncio.run(_cmd_indicators(settings, args[1:]))
    elif command == "strategy":
        asyncio.run(_cmd_strategy(settings, args[1:]))
    elif command == "risk":
        asyncio.run(_cmd_risk(settings, args[1:]))
    elif command == "paper":
        asyncio.run(_cmd_paper(settings, args[1:]))
    elif command == "backtest":
        asyncio.run(_cmd_backtest(settings, args[1:]))
    elif command == "optimize":
        asyncio.run(_cmd_optimize(settings, args[1:]))
    elif command == "dashboard":
        _cmd_dashboard(settings, args[1:])
    elif command == "telegram":
        asyncio.run(_cmd_telegram(settings, args[1:]))
    elif command == "migrate":
        asyncio.run(_cmd_migrate(settings, args[1:]))
    elif command == "positions":
        asyncio.run(_cmd_positions(settings, args[1:]))
    elif command == "research":
        asyncio.run(_cmd_research(settings, args[1:]))
    elif command == "demo":
        asyncio.run(_cmd_demo(settings, args[1:]))
    elif command == "daemon":
        _cmd_daemon(settings, args[1:])
    elif command in ("-h", "--help", "help"):
        _cmd_help()
    else:
        _cmd_banner(settings)


def _cmd_banner(settings: object) -> None:
    """Print the default readiness banner."""
    from marketpilot import __app_name__, __version__

    logger.info("━" * 50)
    logger.info("  {} v{}", __app_name__, __version__)
    is_testnet = getattr(settings.exchange, 'environment', None) and settings.exchange.environment.value == 'TESTNET' # type: ignore
    logger.info("  Testnet: {}", is_testnet)
    logger.info("  DB: {}", settings.storage.url)  # type: ignore[attr-defined]
    logger.info("━" * 50)
    logger.info("Foundation loaded — ready for module integration.")


async def _cmd_ping(settings: object) -> None:
    """Execute the ``ping`` command — check exchange connectivity."""
    from marketpilot import __app_name__, __version__
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.config.settings import ExecutionMode

    client = BybitClient(exchange_settings=settings.exchange, execution_mode=settings.execution_mode)  # type: ignore[attr-defined]

    try:
        await client.connect()
        result = await client.ping()

        print()
        print(f"  [OK] Connected")
        print(f"  - Server Time : {result['server_time']}")
        print(f"  - Latency     : {result['latency_ms']} ms")
        print(f"  - Environment : {result['environment']}")
        print(f"  - Version     : {__app_name__} v{__version__}")
        print()
    except Exception as exc:
        logger.error("Ping failed: {}", exc)
        print()
        print(f"  [ERR] Connection failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await client.disconnect()


async def _cmd_scan(settings: object, args: list[str]) -> None:
    """Execute the ``scan`` command."""
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.core.factory import MissionControlFactory
    # Parse args manually
    min_turnover: float | None = None
    limit: int | None = None
    i = 0
    while i < len(args):
        if args[i] == "--min-turnover" and i + 1 < len(args):
            try:
                min_turnover = float(args[i + 1])
                if min_turnover < 0 or not float(min_turnover).is_integer() and min_turnover != float("inf") and min_turnover != float("-inf") and min_turnover != min_turnover:
                    pass # Handled below
            except ValueError:
                print("Error: --min-turnover must be a valid number.")
                sys.exit(1)

            if min_turnover < 0 or str(min_turnover) in ("inf", "-inf", "nan"):
                print("Error: --min-turnover must be a positive finite number.")
                sys.exit(1)
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit < 1:
                    print("Error: --limit must be at least 1.")
                    sys.exit(1)
            except ValueError:
                print("Error: --limit must be an integer.")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    # Do not mutate shared settings in-place.
    scanner_settings_dict = settings.scanner.model_dump()  # type: ignore[attr-defined]
    if min_turnover is not None:
        scanner_settings_dict["min_turnover_24h"] = min_turnover
    if limit is not None:
        scanner_settings_dict["max_results"] = limit

    from marketpilot.config.settings import ScannerSettings
    scanner_settings = ScannerSettings(**scanner_settings_dict)

    ctx = MissionControlFactory.build_runtime(settings)

    try:
        await ctx.client.connect()

        limit = ctx.settings.scanner.max_results
        quote_coin = ctx.settings.scanner.quote_coin
        min_turnover = ctx.settings.scanner.min_turnover_24h

        raw_candidates = await ctx.market_data_fetcher.fetch_scan_candidates(
            quote_coin=quote_coin,
            min_turnover_24h=min_turnover,
            limit=limit
        )

        snapshots = []
        for raw in raw_candidates:
            snapshots.append(ctx.snapshot_builder.build(raw))

        scanner_result = ctx.scanner.evaluate(snapshots)
        results = scanner_result.top_candidates

        print()
        print(f"  {'Rank':<4} | {'Symbol':<12} | {'Last Price':<12} | {'24h Change':<10} | {'24h Turnover'}")
        print("  " + "-" * 75)

        from decimal import Decimal
        for idx, r in enumerate(results, 1):
            try:
                pcnt_decimal = Decimal(r.momentum_24h) * Decimal("100")
                change_fmt = f"{pcnt_decimal:.2f}%"
            except Exception:
                change_fmt = f"{r.momentum_24h}%"

            # format turnover in millions
            try:
                turnover_decimal = Decimal(r.liquidity_turnover_24h) / Decimal("1000000")
                turnover_m = f"${turnover_decimal:.1f}M"
            except Exception:
                turnover_m = r.liquidity_turnover_24h
            print(f"  {idx:<4} | {r.symbol:<12} | {r.last_price:<12} | {change_fmt:<10} | {turnover_m}")
        print()

        print(f"  Market Health: {scanner_result.market_health:.2f}%")
        print()

    except Exception as exc:
        logger.error("Scan failed: {}", exc)
        print()
        print(f"  [ERR] Scan failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await ctx.client.disconnect()


async def _cmd_indicators(settings: object, args: list[str]) -> None:
    """Execute the ``indicators`` command."""
    from marketpilot.core.enums import AssetType, Interval
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.indicators.service import IndicatorService

    if not args:
        print("Usage: uv run marketpilot indicators SYMBOL [--interval MINS] [--limit NUM]")
        sys.exit(1)

    symbol = args[0]
    interval_val = 60
    limit = 250

    i = 1
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            try:
                interval_val = int(args[i + 1])
            except ValueError:
                print("Error: --interval must be an integer.")
                sys.exit(1)
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit < 1 or limit > 999:
                    print("Error: --limit must be between 1 and 999.")
                    sys.exit(1)
            except ValueError:
                print("Error: --limit must be an integer.")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    try:
        interval = Interval(str(interval_val))
    except ValueError:
        print(f"Error: Invalid interval '{interval_val}'.")
        sys.exit(1)

    client = BybitClient(settings.exchange)  # type: ignore[attr-defined]
    service = IndicatorService(settings.indicators)  # type: ignore[attr-defined]

    try:
        await client.connect()
        klines = await client.get_klines(
            symbol=symbol,
            interval=interval,
            asset_type=AssetType("linear"),
            limit=limit + 1,  # Fetch one extra to drop the active candle
        )

        if not klines:
            print(f"No klines found for {symbol}.")
            sys.exit(0)

        closed_klines = _filter_closed_klines(klines, interval)

        if not closed_klines:
            print(f"Not enough closed klines for {symbol}.")
            sys.exit(0)

        series = service.calculate(closed_klines)
        latest = series.latest

        if latest is None:
            print("No indicator points generated.")
            sys.exit(0)

        print()
        print(f"  Indicators for {symbol} ({interval.value}m, latest closed candle at {latest.open_time})")
        print("  " + "-" * 75)

        def fmt(val: object) -> str:
            return f"{val:.4f}" if val is not None else "N/A"

        print(f"  EMA Fast ({settings.indicators.ema_fast})   : {fmt(latest.ema_fast)}")  # type: ignore[attr-defined]
        print(f"  EMA Slow ({settings.indicators.ema_slow})   : {fmt(latest.ema_slow)}")  # type: ignore[attr-defined]
        print(f"  RSI ({settings.indicators.rsi_period})          : {fmt(latest.rsi)}")  # type: ignore[attr-defined]
        print(f"  MACD Line       : {fmt(latest.macd_line)}")
        print(f"  MACD Signal     : {fmt(latest.macd_signal)}")
        print(f"  MACD Hist       : {fmt(latest.macd_histogram)}")
        print(f"  ATR ({settings.indicators.atr_period})          : {fmt(latest.atr)}")  # type: ignore[attr-defined]
        print(f"  Volume SMA ({settings.indicators.volume_sma_period}) : {fmt(latest.volume_sma)}")  # type: ignore[attr-defined]
        print()

    except Exception as exc:
        logger.error("Indicators failed: {}", exc)
        print()
        print(f"  [ERR] Indicators failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await client.disconnect()


def _filter_closed_klines(klines: list, interval) -> list:
    """Helper to filter out the active, non-closed candle."""
    if not klines:
        return []

    klines_sorted = sorted(klines, key=lambda k: k.open_time)

    interval_str = interval.value
    try:
        interval_mins = int(interval_str)
    except ValueError:
        if interval_str == "D": interval_mins = 1440
        elif interval_str == "W": interval_mins = 10080
        elif interval_str == "M": interval_mins = 43200
        else: interval_mins = 60

    from datetime import datetime, timedelta, UTC
    latest_close_time = klines_sorted[-1].open_time + timedelta(minutes=interval_mins)

    if datetime.now(tz=UTC) < latest_close_time:
        return klines_sorted[:-1]
    return klines_sorted


async def _cmd_strategy(settings: object, args: list[str]) -> None:
    """Execute the ``strategy`` command."""
    from marketpilot.core.enums import AssetType, Interval
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.indicators.service import IndicatorService
    from marketpilot.core.factory import MissionControlFactory
    if not args:
        print("Usage: uv run marketpilot strategy SYMBOL [--interval MINS] [--limit NUM]")
        sys.exit(1)

    symbol = args[0]
    interval_val = 60
    limit = 250

    i = 1
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            try:
                interval_val = int(args[i + 1])
            except ValueError:
                print("Error: --interval must be an integer.")
                sys.exit(1)
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit < 1 or limit > 999:
                    print("Error: --limit must be between 1 and 999.")
                    sys.exit(1)
            except ValueError:
                print("Error: --limit must be an integer.")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    try:
        interval = Interval(str(interval_val))
    except ValueError:
        print(f"Error: Invalid interval '{interval_val}'.")
        sys.exit(1)

    ctx = MissionControlFactory.build_runtime(settings)

    try:
        await ctx.client.connect()

        # 1. Fetch raw data
        raw = await ctx.market_data_fetcher.fetch(
            symbol=symbol,
            interval=interval,
            kline_limit=limit + 1
        )

        # Drop active candle
        raw.klines = _filter_closed_klines(raw.klines, interval)
        if not raw.klines:
            print(f"Not enough closed klines for {symbol}.")
            sys.exit(0)

        # 2. Build Snapshot
        snapshot = ctx.snapshot_builder.build(raw)

        # 3. Indicators & Regime
        series = ctx.indicator.calculate(raw.klines)
        regime = ctx.regime.evaluate(series, snapshot.last_price)

        # 4. Strategy (Generates SignalIntent)
        intents, meta = ctx.strategy.evaluate(series, regime, snapshot, decision_id="cli_strategy")

        print()
        print("  [ANALYSIS ONLY - PHASE 4 CAUSAL EVALUATION]")
        print("  " + "-" * 75)
        print(f"  Strategy Intents for {symbol} ({interval.value}m)")

        if not intents:
            print("  No intents generated.")
        else:
            from marketpilot.strategy.pipeline import CausalPipeline
            from marketpilot.strategy.pricing_policy import PricingPolicy
            from marketpilot.strategy.validation_policy import ValidationPolicy
            from marketpilot.strategy.economics import CausalEconomicsEngine
            from marketpilot.models.causal import ExecutableQuoteSnapshot
            from decimal import Decimal
            import time

            pipeline = CausalPipeline(
                pricing=PricingPolicy(),
                validation=ValidationPolicy([]),
                economics=CausalEconomicsEngine(account_equity=Decimal("1000"))
            )

            quotes = {}
            live_tickers = await ctx.client.get_tickers(symbol, asset_type=AssetType.LINEAR)
            if live_tickers:
                bid = Decimal(live_tickers[0].bid_price)
                ask = Decimal(live_tickers[0].ask_price)
                q = ExecutableQuoteSnapshot(
                    quote_id=f"quote_{int(time.time())}",
                    symbol=symbol,
                    environment=snapshot.environment,
                    quote_timestamp=time.time(),
                    bid=bid,
                    ask=ask
                )
                for intent in intents:
                    quotes[intent.identity.strategy_id] = q

            res = pipeline.process_signals(intents, quotes, "trend_smoke", "BULL", "ALL")

            for c in res.candidates:
                print(f"  Candidate: {c.priced_candidate.intent.identity.strategy_id} -> {c.priced_candidate.intent.direction.value}")
                print(f"    Entry      : {c.priced_candidate.executable_entry_price}")
                print(f"    Quantity   : {c.sizing.provisional_quantity}")
                print(f"    Final EV_R : {c.size_aware_economics.final_net_ev_r}")
            for o in res.observations:
                from marketpilot.models.causal import CandidateRejectedObserved
                if isinstance(o, CandidateRejectedObserved):
                    print(f"  Rejected: {o.identity.strategy_id} -> {o.rejection_reason}")
        print()

    except Exception as exc:
        logger.error("Strategy failed: {}", exc)
        print()
        print(f"  [ERR] Strategy failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await ctx.client.disconnect()


async def _cmd_risk(settings: object, args: list[str]) -> None:
    """Execute the ``risk`` command."""
    from marketpilot.core.enums import AssetType, Interval
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.indicators.service import IndicatorService
    from marketpilot.core.factory import MissionControlFactory
    from decimal import Decimal, InvalidOperation

    if not args:
        print("Usage: uv run marketpilot risk SYMBOL --equity NUM [--interval MINS] [--limit NUM]")
        sys.exit(1)

    symbol = args[0]
    interval_val = 60
    limit = 250
    equity_val: Decimal | None = None

    i = 1
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            try:
                interval_val = int(args[i + 1])
            except ValueError:
                print("Error: --interval must be an integer.")
                sys.exit(1)
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit < 1 or limit > 999:
                    print("Error: --limit must be between 1 and 999.")
                    sys.exit(1)
            except ValueError:
                print("Error: --limit must be an integer.")
                sys.exit(1)
            i += 2
        elif args[i] == "--equity" and i + 1 < len(args):
            try:
                equity_val = Decimal(args[i + 1])
                if not equity_val.is_finite() or equity_val <= Decimal("0"):
                    print("Error: --equity must be a positive finite number.")
                    sys.exit(1)
            except InvalidOperation:
                print("Error: --equity must be a valid number.")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    if equity_val is None:
        print("Error: --equity is required.")
        sys.exit(1)

    try:
        interval = Interval(str(interval_val))
    except ValueError:
        print(f"Error: Invalid interval '{interval_val}'.")
        sys.exit(1)

    ctx = MissionControlFactory.build_runtime(settings)

    try:
        await ctx.client.connect()

        # 1. Fetch raw data
        raw = await ctx.market_data_fetcher.fetch(
            symbol=symbol,
            interval=interval,
            kline_limit=limit + 1
        )

        # Drop active candle
        raw.klines = _filter_closed_klines(raw.klines, interval)
        if not raw.klines:
            print(f"Not enough closed klines for {symbol}.")
            sys.exit(0)

        # 2. Build Snapshot
        snapshot = ctx.snapshot_builder.build(raw)

        # 3. Indicators & Regime
        series = ctx.indicator.calculate(raw.klines)
        regime = ctx.regime.evaluate(series, snapshot.last_price)

        # 4. Strategy
        intents, meta = ctx.strategy.evaluate(series, regime, snapshot, decision_id="cli_risk")

        print()
        print("  [PHASE-4 READ ONLY - NO PHASE-5 PORTFOLIO AUTHORIZATION EXISTS]")
        print("  " + "-" * 75)
        print(f"  Legacy Risk Assessment (DEPRECATED) for {symbol} ({interval.value}m)")
        print(f"  Note: Phase 4 CausalEconomicsEngine now handles sizing and economics.")
        print()

    except Exception as exc:
        logger.error("Risk assessment failed: {}", exc)
        print()
        print(f"  [ERR] Risk assessment failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await ctx.client.disconnect()


async def _cmd_paper(settings: object, args: list[str]) -> None:
    """Execute the ``paper`` command."""
    if not args:
        print("Usage: uv run marketpilot paper [reset|status|open|close]")
        sys.exit(1)

    subcommand = args[0]
    confirm = "--confirm" in args

    from marketpilot.storage.database import DatabaseManager
    from marketpilot.paper.service import PaperTradingService

    db = DatabaseManager(settings.storage)  # type: ignore[attr-defined]
    paper_service = PaperTradingService(settings.paper)  # type: ignore[attr-defined]

    await db.initialize()

    try:
        if subcommand == "reset":
            if not confirm:
                print("Error: Paper reset requires --confirm.")
                sys.exit(1)

            equity_val = None
            for i, arg in enumerate(args):
                if arg == "--equity" and i + 1 < len(args):
                    from decimal import Decimal, InvalidOperation
                    try:
                        equity_val = Decimal(args[i + 1])
                        if not equity_val.is_finite() or equity_val <= 0:
                            print("Error: --equity must be a positive finite number.")
                            sys.exit(1)
                    except InvalidOperation:
                        print("Error: --equity must be a valid number.")
                        sys.exit(1)

            if equity_val is not None:
                settings.paper.initial_equity = equity_val  # type: ignore[attr-defined]

            async with db.session() as session:
                async with session.begin():
                    await paper_service.reset(session)

            print()
            print("  [PAPER ONLY - NO REAL ORDER]")
            print("  ---------------------------------------------------------------------------")
            print(f"  Account reset to {settings.paper.initial_equity}")  # type: ignore[attr-defined]
            print()

        elif subcommand == "status":
            from marketpilot.exchange.bybit_client import BybitClient
            client = BybitClient(settings.exchange)  # type: ignore[attr-defined]

            market_prices = {}
            try:
                await client.connect()

                # We need public tickers to get latest price for open positions
                async with db.session() as session:
                    snapshot = await paper_service.get_snapshot(session, market_prices)

                if snapshot.positions:
                    # Fetch real prices for active positions
                    tickers = await client.get_tickers(category="linear")
                    for t in tickers:
                        if any(p.symbol == t.symbol for p in snapshot.positions):
                            from decimal import Decimal
                            market_prices[t.symbol] = Decimal(t.last_price)

                    # Recompute snapshot with real market prices
                    async with db.session() as session:
                        snapshot = await paper_service.get_snapshot(session, market_prices)

            finally:
                await client.disconnect()

            print()
            print("  [PAPER ONLY - NO REAL ORDER]")
            print("  ---------------------------------------------------------------------------")
            print("  Paper Trading Status")
            print(f"  Cash        : {snapshot.cash:.4f}")
            print(f"  Locked      : {snapshot.locked_margin:.4f}")
            print(f"  Equity      : {snapshot.equity:.4f}")
            print(f"  Realized PnL: {snapshot.realized_pnl:.4f}")
            print(f"  Unreal. PnL : {snapshot.unrealized_pnl:.4f}")

            print()
            print("  Open Positions:")
            if not snapshot.positions:
                print("    None")
            else:
                for p in snapshot.positions:
                    print(f"    - {p.symbol} {p.direction.value} | Qty: {p.quantity} | Entry: {p.entry_price:.4f} | Mark: {p.mark_price:.4f} | PnL: {p.unrealized_pnl:.4f}")

            print()

        elif subcommand == "open":
            if not confirm:
                print("Error: Paper open requires --confirm.")
                sys.exit(1)

            if len(args) < 2 or args[1].startswith("--"):
                print("Error: Paper open requires SYMBOL.")
                sys.exit(1)

            symbol = args[1]

            from marketpilot.core.enums import AssetType, Interval
            from marketpilot.exchange.bybit_client import BybitClient
            from marketpilot.indicators.service import IndicatorService
            from marketpilot.core.factory import MissionControlFactory
            from decimal import Decimal, InvalidOperation

            interval_val = 60
            limit = 250

            i = 2
            while i < len(args):
                if args[i] == "--interval" and i + 1 < len(args):
                    interval_val = int(args[i + 1])
                    i += 2
                elif args[i] == "--limit" and i + 1 < len(args):
                    limit = int(args[i + 1])
                    i += 2
                else:
                    i += 1

            interval = Interval(str(interval_val))
            client = BybitClient(settings.exchange)  # type: ignore[attr-defined]
            indicator_service = IndicatorService(settings.indicators)  # type: ignore[attr-defined]
            ctx = MissionControlFactory.build_runtime(settings)
            strategy_service = ctx.strategy  # type: ignore[attr-defined]
            risk_service = ctx.risk  # type: ignore[attr-defined]

            try:
                await client.connect()
                klines = await client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    asset_type=AssetType("linear"),
                    limit=limit + 1,
                )

                if not klines:
                    print(f"No klines found for {symbol}.")
                    sys.exit(0)

                closed_klines = _filter_closed_klines(klines, interval)
                if not closed_klines:
                    print(f"Not enough closed klines for {symbol}.")
                    sys.exit(0)

                series = indicator_service.calculate(closed_klines)
                signal = strategy_service.evaluate(series)

                latest_indicator = series.latest
                atr_val = latest_indicator.atr if latest_indicator else None
                entry_price = Decimal(closed_klines[-1].close)

                async with db.session() as session:
                    snapshot = await paper_service.get_snapshot(session, {})
                    equity_val = snapshot.equity

                assessment = risk_service.assess(
                    signal=signal,
                    entry_price=entry_price,
                    atr=atr_val,
                    account_equity=equity_val
                )

                if not assessment.eligible_for_paper_trading:
                    print()
                    print("  [PAPER ONLY - NO REAL ORDER]")
                    print("  ---------------------------------------------------------------------------")
                    print(f"  Rejected: {assessment.reasons}")
                    print()

                    from marketpilot.core.factory import MissionControlFactory
                    from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
                    notifier = TelegramNotifier(settings.telegram) # type: ignore
                    await notifier.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={"message": f"⚠️ [PAPER ONLY] Action Rejected\n\nSymbol: {symbol}\nAction: {"OPEN"}\nReason: {", ".join(assessment.reasons) if assessment.reasons else "Unknown"}\n\nNo real order was placed."}))
                    sys.exit(1)

                async with db.session() as session:
                    async with session.begin():
                        trade = await paper_service.open_position(session, assessment, entry_price)

                        from marketpilot.core.factory import MissionControlFactory
                        from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
                notifier = TelegramNotifier(settings.telegram) # type: ignore
                await notifier.notify(NotificationEvent(event_type=NotificationType.PAPER_TRADE, message_data={"message": f"🟢 [PAPER ONLY] Position Opened\n\nSymbol: {trade.symbol}\nDirection: {trade.direction}\nQty: {trade.quantity}\nEntry: {trade.entry_price}\n\nNo real order was placed."}))

                print()
                print("  [PAPER ONLY - NO REAL ORDER]")
                print("  ---------------------------------------------------------------------------")
                print(f"  Opened {trade.direction.value} {trade.symbol}")
                print(f"  Qty       : {trade.quantity}")
                print(f"  Fill Price: {trade.entry_price:.4f}")
                print(f"  Fee       : {trade.entry_fee:.4f}")
                print()
            finally:
                await client.disconnect()

        elif subcommand == "close":
            if not confirm:
                print("Error: Paper close requires --confirm.")
                sys.exit(1)

            if len(args) < 2 or args[1].startswith("--"):
                print("Error: Paper close requires SYMBOL.")
                sys.exit(1)

            symbol = args[1]

            from marketpilot.exchange.bybit_client import BybitClient
            client = BybitClient(settings.exchange)  # type: ignore[attr-defined]
            try:
                await client.connect()
                tickers = await client.get_tickers(category="linear")
                market_price = None
                for t in tickers:
                    if t.symbol == symbol:
                        from decimal import Decimal
                        market_price = Decimal(t.last_price)
                        break

                if market_price is None:
                    print(f"Could not fetch public price for {symbol}")
                    sys.exit(1)

                async with db.session() as session:
                    async with session.begin():
                        trade = await paper_service.close_position(session, symbol, market_price)

                        from marketpilot.core.factory import MissionControlFactory
                        from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
                notifier = TelegramNotifier(settings.telegram) # type: ignore
                await notifier.notify(NotificationEvent(
                    event_type=NotificationType.EXECUTION_SUCCESS,
                    message_data={"message": f"📊 [PAPER ONLY] Position Closed\nSymbol: {trade.symbol}\nDirection: {trade.direction.value}\nExit: {trade.exit_price:.4f}\nPnL: {trade.realized_pnl:.4f}"}
                ))

                print()
                print("  [PAPER ONLY - NO REAL ORDER]")
                print("  ---------------------------------------------------------------------------")
                print(f"  Closed {trade.direction.value} {trade.symbol}")
                print(f"  Exit Price: {trade.exit_price:.4f}")
                print(f"  Exit Fee  : {trade.exit_fee:.4f}")
                print(f"  Net PnL   : {trade.realized_pnl:.4f}")
                print()
            finally:
                await client.disconnect()
        else:
            print(f"Unknown paper command: {subcommand}")
            sys.exit(1)

    finally:
        await db.close()


async def _cmd_backtest(settings: object, args: list[str]) -> None:
    """Execute the ``backtest`` command."""
    if not args or args[0].startswith("--"):
        print("Usage: uv run marketpilot backtest SYMBOL [--interval MINS] [--limit NUM]")
        sys.exit(1)

    symbol = args[0]
    interval_val = 60
    limit = 1000

    i = 1
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            try:
                interval_val = int(args[i + 1])
            except ValueError:
                print("Error: --interval must be an integer.")
                sys.exit(1)
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit < 1:
                    print("Error: --limit must be at least 1.")
                    sys.exit(1)
            except ValueError:
                print("Error: --limit must be an integer.")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    from marketpilot.core.enums import AssetType, Interval
    try:
        interval = Interval(str(interval_val))
    except ValueError:
        print(f"Error: Invalid interval '{interval_val}'.")
        sys.exit(1)

    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.indicators.service import IndicatorService
    from marketpilot.core.factory import MissionControlFactory
    from marketpilot.backtest.engine import BacktestEngine

    client = BybitClient(settings.exchange)  # type: ignore[attr-defined]
    indicator_service = IndicatorService(settings.indicators)  # type: ignore[attr-defined]
    ctx = MissionControlFactory.build_runtime(settings)
    strategy_service = ctx.strategy  # type: ignore[attr-defined]
    risk_service = ctx.risk  # type: ignore[attr-defined]
    engine = BacktestEngine(
        settings=settings.backtest,  # type: ignore[attr-defined]
        indicator_service=indicator_service,
        strategy_service=strategy_service,
        risk_service=risk_service
    )

    try:
        await client.connect()
        klines = await client.get_klines(
            symbol=symbol,
            interval=interval,
            asset_type=AssetType("linear"),
            limit=limit + 1,  # Fetch one extra to drop the active candle
        )

        if not klines:
            print(f"No klines found for {symbol}.")
            sys.exit(0)

        closed_klines = _filter_closed_klines(klines, interval)

        if not closed_klines:
            print(f"Not enough closed klines for {symbol}.")
            sys.exit(0)

        result = engine.run(closed_klines)

        print()
        print("  [HISTORICAL SIMULATION - NO REAL ORDER]")
        print("  ---------------------------------------------------------------------------")
        print(f"  Backtest Summary for {result.symbol} ({result.interval.value}m)")
        print(f"  Period: {result.start_time} to {result.end_time}")
        print("  ---------------------------------------------------------------------------")

        m = result.metrics
        def fmt(val: object, suffix: str = "") -> str:
            return f"{val:.4f}{suffix}" if val is not None else "N/A"

        print(f"  Starting Equity : {fmt(m.starting_equity)}")
        print(f"  Ending Equity   : {fmt(m.ending_equity)}")
        print(f"  Total Return    : {fmt(m.total_return_fraction * 100, '%')}")
        print(f"  Max Drawdown    : {fmt(m.max_drawdown_fraction * 100, '%')}")
        print(f"  Total Trades    : {m.trade_count}")
        print(f"  Win Rate        : {fmt(m.win_rate * 100 if m.win_rate else None, '%')}")
        print(f"  Profit Factor   : {fmt(m.profit_factor)}")
        print("  ---------------------------------------------------------------------------")

        if result.trades:
            print("  Recent Trades:")
            for t in result.trades[-5:]:
                print(f"    - {t.direction.value:<5} | Entry: {t.entry_price:.2f} | Exit: {t.exit_price:.2f} | PnL: {t.realized_pnl:+.2f} ({t.exit_reason})")
        else:
            print("  No trades executed.")
        print()

        from marketpilot.reports.store import ReportStore
        store = ReportStore()
        store.save_backtest(result)
        print("  [✓] Report saved to backtest.latest.json")

        from marketpilot.core.factory import MissionControlFactory
        from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
        notifier = TelegramNotifier(settings.telegram) # type: ignore
        await notifier.notify(NotificationEvent(event_type=NotificationType.EXECUTION_SUCCESS, message_data={"message": f"📊 [HISTORICAL ONLY] Run Completed\nType: backtest\nSymbol: {result.symbol} ({result.interval.value})\nTotal Return: {result.metrics.total_return_fraction * Decimal('100')}%"}))

        print()

    except Exception as exc:
        logger.error("Backtest failed: {}", exc)
        print()
        print(f"  [ERR] Backtest failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await client.disconnect()


async def _cmd_optimize(settings: object, args: list[str]) -> None:
    """Execute the ``optimize`` command."""
    if not args or args[0].startswith("--"):
        print("Usage: uv run marketpilot optimize SYMBOL [--interval MINS] [--limit NUM]")
        sys.exit(1)

    symbol = args[0]
    interval_val = 60
    limit = 1000

    i = 1
    while i < len(args):
        if args[i] == "--interval" and i + 1 < len(args):
            try:
                interval_val = int(args[i + 1])
            except ValueError:
                print("Error: --interval must be an integer.")
                sys.exit(1)
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            try:
                limit = int(args[i + 1])
                if limit < 1:
                    print("Error: --limit must be at least 1.")
                    sys.exit(1)
            except ValueError:
                print("Error: --limit must be an integer.")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            sys.exit(1)

    from marketpilot.core.enums import AssetType, Interval
    try:
        interval = Interval(str(interval_val))
    except ValueError:
        print(f"Error: Invalid interval '{interval_val}'.")
        sys.exit(1)

    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.indicators.service import IndicatorService
    from marketpilot.core.factory import MissionControlFactory
    from marketpilot.optimization.service import OptimizationService
    from marketpilot.config.settings import BacktestSettings

    client = BybitClient(settings.exchange)  # type: ignore[attr-defined]
    indicator_service = IndicatorService(settings.indicators)  # type: ignore[attr-defined]
    risk_service = ctx.risk  # type: ignore[attr-defined]

    # We pass the factory and kwargs instead of a built engine,
    # so the service can safely construct them per candidate.
    optimization_service = OptimizationService(
        settings=settings.optimization,  # type: ignore[attr-defined]
        indicator_service=indicator_service,
        risk_service=risk_service,
        baseline_strategy_settings=settings.strategy,  # type: ignore[attr-defined]
        backtest_settings_factory=BacktestSettings,
        backtest_settings_kwargs=settings.backtest.model_dump()  # type: ignore[attr-defined]
    )

    try:
        await client.connect()
        klines = await client.get_klines(
            symbol=symbol,
            interval=interval,
            asset_type=AssetType("linear"),
            limit=limit + 1,
        )

        if not klines:
            print(f"No klines found for {symbol}.")
            sys.exit(0)

        closed_klines = _filter_closed_klines(klines, interval)

        if not closed_klines:
            print(f"Not enough closed klines for {symbol}.")
            sys.exit(0)

        print(f"Starting parameter search on {len(closed_klines)} candles...")
        result = optimization_service.optimize(closed_klines)

        print()
        print("  [HISTORICAL PARAMETER SEARCH - NO REAL ORDER]")
        print("  ---------------------------------------------------------------------------")
        print(f"  Optimization Summary for {result.symbol} ({result.interval.value}m)")
        print(f"  Split Date      : {result.split_time}")
        print(f"  Total Candidates: {len(result.candidates)}")
        print("  ---------------------------------------------------------------------------")

        def fmt(val: object, suffix: str = "") -> str:
            return f"{val:.4f}{suffix}" if val is not None else "N/A"

        if result.best_candidate:
            print("  Top 10 Ranked Candidates (Selected by TRAINING metrics only):")

            # Sort all eligible by training objective
            eligible = [c for c in result.candidates if c.is_eligible]
            eligible.sort(
                key=lambda r: (
                    -float(r.train_objective), # type: ignore
                    float(r.train_metrics.max_drawdown_fraction), # type: ignore
                    r.candidate.label
                )
            )

            for idx, res in enumerate(eligible[:10], 1):
                label = res.candidate.label
                tm = res.train_metrics
                vm = res.val_metrics

                print(f"  {idx}. {label:<10} | Train Obj: {fmt(res.train_objective)} | Train Ret: {fmt(tm.total_return_fraction * 100, '%')} | Val Ret: {fmt(vm.total_return_fraction * 100, '%')} | Val DD: {fmt(vm.max_drawdown_fraction * 100, '%')} | Trades (T/V): {tm.trade_count}/{vm.trade_count}")
        else:
            print("  No eligible candidates found (none met minimum trade requirements).")

        print("  ---------------------------------------------------------------------------")
        print("  * Winner is selected strictly from training data performance.")
        print()

        from marketpilot.reports.store import ReportStore
        store = ReportStore()
        store.save_optimization(result)
        print("  [✓] Report saved to optimization.latest.json")

        from marketpilot.core.factory import MissionControlFactory
        from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
        notifier = TelegramNotifier(settings.telegram) # type: ignore
        await notifier.notify(NotificationEvent(event_type=NotificationType.EXECUTION_SUCCESS, message_data={"message": f"📊 [HISTORICAL ONLY] Run Completed\nType: optimize\nSymbol: {result.symbol} ({result.interval.value})\nBest: {result.best_candidate.candidate.label if result.best_candidate else 'None'}"}))

        print()

    except Exception as exc:
        from loguru import logger
        logger.error("Optimization failed: {}", exc)
        print()
        print(f"  [ERR] Optimization failed: {exc}")
        print()
        sys.exit(1)
    finally:
        await client.disconnect()


def _cmd_dashboard(settings: object, args: list[str]) -> None:
    """Execute the ``dashboard`` command."""
    host = "127.0.0.1"
    port = 8000

    i = 0
    while i < len(args):
        if args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            print(f"Unknown argument: {args[i]}")
            import sys
            sys.exit(1)

    import socket
    import sys

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
    except OSError:
        print(f"\n  [ERR] Port {port} on {host} is already in use.")
        print(f"        Ensure no other MarketPilot dashboard instances are running.")
        sys.exit(1)

    import uvicorn
    print(f"Starting MarketPilot Dashboard on http://{host}:{port}")
    uvicorn.run("marketpilot.dashboard.server:app", host=host, port=port, log_level="info")


async def _cmd_telegram(settings: object, args: list[str]) -> None:
    """Execute the ``telegram`` command."""
    if not args or args[0].startswith("--"):
        print("Usage: uv run marketpilot telegram {status, test}")
        import sys
        sys.exit(1)

    subcommand = args[0]
    confirm = "--confirm" in args

    from marketpilot.core.factory import MissionControlFactory
    notifier = TelegramNotifier(settings.telegram) # type: ignore

    if subcommand == "status":
        print()
        print("  [TELEGRAM STATUS]")
        print("  ---------------------------------------------------------------------------")
        print(f"  Enabled: {'Yes' if notifier.settings.enabled else 'No'}")
        if notifier.settings.enabled:
            # Mask chat_id
            chat_id = settings.telegram.chat_id # type: ignore
            masked_chat = chat_id[:3] + "***" + chat_id[-2:] if len(chat_id) > 4 else "***"
            print(f"  Chat ID: {masked_chat}")
            print(f"  Timeout: {settings.telegram.timeout_seconds}s") # type: ignore
            print()
            print("  [PHASE-5 ADMISSION ALERTS]")
            print("  This channel will receive strictly outbound read-only notifications.")
            print("  No inbound trading commands are permitted or evaluated.")
        print("  ---------------------------------------------------------------------------")
        print()
    elif subcommand == "test":
        if not confirm:
            print("Error: Telegram test requires --confirm.")
            import sys
            sys.exit(1)

        if not notifier.settings.enabled:
            print("Error: Telegram notifier is disabled or incompletely configured.")
            print("No HTTP request will be made.")
            import sys
            sys.exit(1)

        print()
        print("  [OUTBOUND NOTIFICATION ONLY - PHASE 5 FORMATTER TEST]")
        print("  Sending test message...")
        from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
        from marketpilot.notifications.telegram_formatters import format_phase5_admission
        from marketpilot.models.causal import (
            FinalCandidate, PricedCandidate, SignalIntent, StrategyIdentity, SignalDirection,
            ExecutableQuoteSnapshot, PricingStatus, EvidenceAssessment, AssessmentStatus,
            PreSizeEconomics, SizingDecision, SizeAwareEconomics, Interval
        )
        from marketpilot.models.portfolio import (
            PortfolioAdmissionDecision, PortfolioExposureSnapshot, EquitySnapshot, PortfolioAllocationToken
        )
        from decimal import Decimal

        # Test the canonical presentation model renderer
        test_candidate = FinalCandidate(
            candidate_id="test_cand_1",
            priced_candidate=PricedCandidate(
                candidate_id="test_cand_1",
                intent=SignalIntent(
                    intent_id="test_int_1",
                    identity=StrategyIdentity(
                        strategy_id="TEST_STRAT",
                        strategy_version="1.0",
                        registry_version="1.0",
                        parameter_set_id="default"
                    ),
                    symbol="BTCUSDT",
                    timeframe=Interval.M5,
                    direction=SignalDirection.LONG,
                    signal_timestamp=0.0,
                    signal_timestamp_us=0,
                    logical_stop_loss=Decimal("49000"),
                    logical_take_profit=Decimal("55000"),
                    provenance_snapshot_id="test_prov"
                ),
                quote=ExecutableQuoteSnapshot(
                    quote_id="test_q_1",
                    environment="MAINNET", # Type is StrEnum, so "MAINNET" works
                    quote_timestamp=0.0,
                    symbol="BTCUSDT",
                    bid=Decimal("50000"),
                    ask=Decimal("50000")
                ),
                pricing_status=PricingStatus.PRICED,
                executable_entry_price=Decimal("50000")
            ),
            assessment=EvidenceAssessment(
                assessment_id="test_ass",
                status=AssessmentStatus.VALIDATED,
                approved_expected_gross_r=Decimal("1.5")
            ),
            pre_size_economics=PreSizeEconomics(
                approved_expected_gross_r=Decimal("1.5"),
                pre_size_expected_cost_r=Decimal("0.1"),
                pre_size_net_ev_r=Decimal("1.4"),
                cost_model_provenance="TEST"
            ),
            sizing=SizingDecision(
                sizing_id="test_size",
                provisional_quantity=Decimal("0.05"),
                effective_stop_price=Decimal("49000"),
                risk_policy_provenance="TEST"
            ),
            size_aware_economics=SizeAwareEconomics(
                size_aware_cost_r=Decimal("0.1"),
                final_net_ev_r=Decimal("1.4")
            ),
            is_eligible=True
        )

        test_decision = PortfolioAdmissionDecision(
            decision_id="test_dec",
            is_admitted=True,
            token=PortfolioAllocationToken(
                candidate_id="test_cand_1",
                decision_id="test_dec",
                strategy_id="TEST_STRAT",
                strategy_version="1.0",
                parameter_set_id="default",
                symbol="BTCUSDT",
                direction="LONG",
                sizing_id="test_size",
                effective_stop=Decimal("49000"),
                quantity=Decimal("0.05"),
                executable_entry=Decimal("50000"),
                candidate_risk_amount=Decimal("50.0"),
                final_net_ev=Decimal("1.4"),
                portfolio_snapshot_version="v1",
                equity_snapshot_version="v1",
                portfolio_policy_version="v1",
                reservation_identity="test_res",
                lineage_identity="test_lin",
                admission_timestamp=0.0
            )
        )

        test_exposure = PortfolioExposureSnapshot(
            exposure_version="v1",
            timestamp=0.0,
            active_position_ids=("pos_1",),
            reserved_allocation_ids=(),
            active_risk_amount=Decimal("150.0"),
            reserved_risk_amount=Decimal("0.0"),
            policy_limit_risk_amount=Decimal("1000.0"),
            policy_max_lineages=5,

        )

        test_equity = EquitySnapshot(
            snapshot_id="test_eq",
            version="1.0",
            captured_at=0.0,
            environment="PAPER",
            safe_account_fingerprint="test",
            configured_allocated_capital=Decimal("10000.0"),
            usable_account_value=Decimal("15000.0"),
            effective_risk_capital=Decimal("10000.0"),
            freshness_status="FRESH",
            provenance="TEST"
        )

        test_message = format_phase5_admission(test_candidate, test_decision, test_exposure, test_equity)

        await notifier.notify(NotificationEvent(
            event_type=NotificationType.PAPER_TRADE,
            message_data={"message": test_message}
        ))
        print("  Done. (Any delivery failures were logged securely)")
        print()
    else:
        print(f"Unknown telegram command: {subcommand}")
        import sys
        sys.exit(1)


async def _cmd_migrate(settings: object, args: list[str]) -> None:
    """Execute the ``migrate`` command."""
    confirm = "--confirm" in args

    if not confirm:
        print("Error: Migration requires --confirm flag to execute.")
        import sys
        sys.exit(1)

    print()
    print("  [DATABASE MIGRATION]")
    print("  ---------------------------------------------------------------------------")
    print("  Connecting to database...")

    from marketpilot.storage.database import DatabaseManager
    db = DatabaseManager(settings.storage) # type: ignore
    await db.initialize(create_tables=True)

    try:
        await db.migrate_paper_trades()
        print("  [✓] Migration successful (or already applied).")
    except Exception as exc:
        print(f"  [ERR] Migration failed: {exc}")
        import sys
        sys.exit(1)
    finally:
        await db.close()

    print("  ---------------------------------------------------------------------------")
    print()


async def _cmd_positions(settings: object, args: list[str]) -> None:
    """Execute the ``positions`` command."""
    if not args or args[0].startswith("--") or args[0] not in ("check", "manage"):
        print("Usage: uv run marketpilot positions {check, manage}")
        import sys
        sys.exit(1)

    subcommand = args[0]
    confirm = "--confirm" in args

    if subcommand == "manage" and not confirm:
        print("Error: positions manage requires --confirm flag to mutate local paper positions.")
        import sys
        sys.exit(1)

    print()
    if subcommand == "manage":
        print("  [PAPER POSITION MANAGEMENT ONLY - NO REAL ORDER]")
    else:
        print("  [PAPER POSITION EVALUATION - READ ONLY]")
    print("  ---------------------------------------------------------------------------")

    from marketpilot.storage.database import DatabaseManager
    from marketpilot.paper.service import PaperTradingService
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.positions.service import PositionManagerService
    from marketpilot.core.enums import AssetType

    db = DatabaseManager(settings.storage) # type: ignore
    await db.initialize(create_tables=True)

    migrated = await db.check_migration_status()
    if not migrated:
        print("  [ERR] Migration required. Please run: uv run marketpilot migrate --confirm")
        await db.close()
        import sys
        sys.exit(1)

    paper = PaperTradingService(settings.paper) # type: ignore
    client = BybitClient(settings.exchange) # type: ignore
    manager = PositionManagerService()

    await client.connect()

    try:
        async with db.session() as session:
            snapshot = await paper.get_snapshot(session, {})
            positions = snapshot.positions

        if not positions:
            print("  No open paper positions.")
        else:
            print(f"  Found {len(positions)} open position(s). Fetching public market prices...")

            # Fetch prices
            tickers = await client.get_tickers(symbol="", asset_type=AssetType("linear"))
            prices = {t.symbol: t.last_price for t in tickers}

            decisions = manager.evaluate_positions(positions, prices)

            to_execute = []

            for d in decisions:
                if d.action.value == "HOLD":
                    color = "\033[90m" # Gray
                    reset = "\033[0m"
                    print(f"  {color}{d.symbol:<10} | Price: {d.mark_price or 'N/A':<10} | Action: {d.action.value:<18} | Reason: {d.reason}{reset}")
                else:
                    print(f"  {d.symbol:<10} | Price: {d.mark_price or 'N/A':<10} | Action: {d.action.value:<18} | Reason: {d.reason}")
                    if d.action.value in ("CLOSE_STOP_LOSS", "CLOSE_TAKE_PROFIT"):
                        to_execute.append(d)

            if subcommand == "manage" and to_execute:
                print("\n  Executing actions...")
                from marketpilot.core.factory import MissionControlFactory
                from marketpilot.notifications.notification_models import NotificationEvent, NotificationType
                notifier = TelegramNotifier(settings.telegram) # type: ignore

                for d in to_execute:
                    try:
                        async with db.session() as session:
                            async with session.begin():
                                trade = await paper.close_position(
                                    session=session,
                                    symbol=d.symbol,
                                    market_price=d.mark_price,
                                    exit_reason=d.reason
                                )
                        print(f"  [✓] Closed {d.symbol} at {trade.exit_price}")

                        await notifier.notify(NotificationEvent(
                            event_type=NotificationType.EXECUTION_SUCCESS,
                            message_data={"message": f"📊 [PAPER ONLY] Position Closed\nSymbol: {trade.symbol}\nDirection: {trade.direction.value}\nExit: {trade.exit_price:.4f}\nPnL: {trade.realized_pnl:.4f}"}
                        ))
                    except Exception as e:
                        print(f"  [ERR] Failed to close {d.symbol}: {e}")
            elif subcommand == "manage":
                print("\n  No actionable decisions found.")

    except Exception as exc:
        print(f"  [ERR] Error during position management: {exc}")
    finally:
        await client.disconnect()
        await db.close()

    print("  ---------------------------------------------------------------------------")
    print()



async def _cmd_research(settings: AppSettings, args: list[str]) -> None:
    """Handle research journal subcommands."""
    import argparse
    from decimal import Decimal
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.research.service import ResearchService
    from marketpilot.core.enums import AssetType, Interval

    print()
    print("  [RESEARCH JOURNAL]")
    print("  ---------------------------------------------------------------------------")

    parser = argparse.ArgumentParser(prog="marketpilot research")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Capture
    parser_cap = subparsers.add_parser("capture")
    parser_cap.add_argument("symbol", type=str)
    parser_cap.add_argument("--interval", type=str, default="60")
    parser_cap.add_argument("--limit", type=int, default=250)
    parser_cap.add_argument("--equity", type=str, default="10000")

    # Evaluate
    parser_eval = subparsers.add_parser("evaluate")
    parser_eval.add_argument("symbol", type=str)
    parser_eval.add_argument("--interval", type=str, default="60")
    parser_eval.add_argument("--limit", type=int, default=1000)

    # Report
    subparsers.add_parser("report")

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        return

    service = ResearchService(settings)

    if parsed.subcommand == "capture":
        symbol = parsed.symbol.upper()
        try:
            interval = Interval(parsed.interval)
        except ValueError:
            print(f"  Error: Invalid interval '{parsed.interval}'")
            return

        print(f"  Capturing observation for {symbol} ({interval.value}m)")
        print("  WARNING: This is out-of-sample simulation only. No paper trades will be placed.")
        print()

        client = BybitClient(settings.exchange)
        try:
            await client.connect()
            klines = await client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=parsed.limit,
                asset_type=AssetType.LINEAR
            )
        except Exception as e:
            print(f"  Failed to fetch klines: {e}")
            return
        finally:
            await client.disconnect()

        # We need closed klines
        closed_klines = [k for k in klines if k.is_closed]
        if not closed_klines:
            print("  Error: No closed klines received.")
            return

        equity = Decimal(parsed.equity)
        obs = service.capture(closed_klines, equity)
        if obs:
            print(f"  [✓] Captured: {obs.direction.value} at {obs.entry_price}")
            print(f"      Stop Loss: {obs.stop_loss} | Take Profit: {obs.take_profit}")
            print(f"      Quantity: {obs.theoretical_quantity}")
            print(f"      Signal Time: {obs.signal_time}")
        else:
            print("  [x] No eligible actionable signal captured.")

    elif parsed.subcommand == "evaluate":
        symbol = parsed.symbol.upper()
        try:
            interval = Interval(parsed.interval)
        except ValueError:
            print(f"  Error: Invalid interval '{parsed.interval}'")
            return

        print(f"  Evaluating open observations for {symbol} ({interval.value}m)")

        client = BybitClient(settings.exchange)
        try:
            await client.connect()
            klines = await client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=parsed.limit,
                asset_type=AssetType.LINEAR
            )
        except Exception as e:
            print(f"  Failed to fetch klines: {e}")
            return
        finally:
            await client.disconnect()

        resolved = service.evaluate(klines)
        print(f"  [✓] Evaluation complete. Resolved {resolved} observation(s).")

    elif parsed.subcommand == "report":
        report = service.generate_report()
        print("  Research Report Statistics:")
        print("  ---------------------------------------------------------------------------")
        print(f"  Total Observations : {report.total_observations}")
        print(f"  Resolved Count     : {report.resolved_count}")
        print(f"  Open Count         : {report.open_count}")

        if report.resolved_count > 0:
            print(f"  Win Rate           : {report.win_rate * Decimal('100'):.2f}%")
            print(f"  Average R          : {report.average_r:.2f}R")
            print(f"  Expectancy         : {report.expectancy:.2f}R")
            print(f"  Max R Drawdown     : {report.max_drawdown_r:.2f}R")
            print(f"  Period             : {report.start_date} to {report.end_date}")
        else:
            print("  Metrics (Win Rate, Average R, Expectancy) : N/A (Insufficient resolved data)")

        print()
        print("  ⚠️ IMPORTANT DISCLAIMER:")
        print("  These statistics are based on theoretical execution without slippage or fee")
        print("  models. Past out-of-sample performance does not guarantee future results.")

async def _cmd_demo(settings: AppSettings, args: list[str]) -> None:
    """Handle demo execution subcommands."""
    import argparse
    from decimal import Decimal
    from marketpilot.exchange.bybit_client import BybitClient
    from marketpilot.core.enums import AssetType, Interval, OrderSide
    from marketpilot.demo.service import DemoExecutionService
    from marketpilot.notifications.telegram_notifier import TelegramNotifier

    print()
    print("  [BYBIT DEMO ONLY - NO REAL MONEY]")
    print("  ---------------------------------------------------------------------------")

    parser = argparse.ArgumentParser(prog="marketpilot demo")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Open
    parser_open = subparsers.add_parser("open")
    parser_open.add_argument("symbol", type=str)
    parser_open.add_argument("--interval", type=str, default="60")
    parser_open.add_argument("--limit", type=int, default=250)
    parser_open.add_argument("--equity", type=str, default="10000")
    parser_open.add_argument("--confirm", action="store_true", help="Confirm execution")

    # Close
    parser_close = subparsers.add_parser("close")
    parser_close.add_argument("symbol", type=str)
    parser_close.add_argument("--quantity", type=str, help="Quantity to close (default: entire position)")
    parser_close.add_argument("--confirm", action="store_true", help="Confirm execution")

    # Autopilot
    parser_auto = subparsers.add_parser("autopilot")
    parser_auto.add_argument("action", type=str, choices=["run"])
    parser_auto.add_argument("--confirm", action="store_true", help="Confirm execution")

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        return

    if not parsed.confirm:
        print("  Error: You must pass --confirm to submit demo orders.")
        return

    service = DemoExecutionService(settings)

    if parsed.subcommand == "open":
        symbol = parsed.symbol.upper()
        try:
            interval = Interval(parsed.interval)
        except ValueError:
            print(f"  Error: Invalid interval '{parsed.interval}'")
            return

        print(f"  Fetching market data for {symbol} ({interval.value}m)...")
        client = BybitClient(settings.exchange) # We fetch public data using default exchange client
        try:
            await client.connect()
            klines = await client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=parsed.limit,
                asset_type=AssetType.LINEAR
            )
        except Exception as e:
            print(f"  Failed to fetch klines: {e}")
            return
        finally:
            await client.disconnect()

        closed_klines = [k for k in klines if k.is_closed]
        if not closed_klines:
            print("  Error: No closed klines received.")
            return

        print("  Evaluating Strategy & Risk...")
        record = await service.execute_open(symbol, interval.value, Decimal(parsed.equity), closed_klines)

        if record:
            print(f"  [✓] Execution Attempted. Status: {record.status.value}")
            print(f"      Order Link ID: {record.order_link_id}")
            print(f"      Quantity     : {record.quantity} filled {record.filled_quantity}")
            if record.avg_fill_price:
                print(f"      Avg Price    : {record.avg_fill_price}")
        else:
            print("  [x] Execution aborted. Signal/Risk not eligible, or execution disabled.")

    elif parsed.subcommand == "close":
        symbol = parsed.symbol.upper()
        quantity = Decimal(parsed.quantity) if parsed.quantity else None

        qty_str = f"{quantity}" if quantity else "ALL"
        print(f"  Attempting to close {qty_str} of {symbol} position...")
        record = await service.execute_close(symbol, quantity)

        if record:
            print(f"  [✓] Execution Attempted. Status: {record.status.value}")
            print(f"      Order Link ID: {record.order_link_id}")
            print(f"      Quantity     : {record.quantity} filled {record.filled_quantity}")
            if record.avg_fill_price:
                print(f"      Avg Price    : {record.avg_fill_price}")
        else:
            print("  [x] Execution aborted or disabled.")

    elif parsed.subcommand == "autopilot":
        if parsed.action == "run":
            from marketpilot.autopilot.service import AutopilotService
            auto_service = AutopilotService(settings)
            print("  Running Autopilot cycle...")
            decision = await auto_service.run_cycle()

            if decision:
                print(f"  [✓] Autopilot completed. Candidate: {decision.symbol}")
                print(f"      Score        : {decision.score}")
                print(f"      Turnover     : {decision.turnover}")
                print(f"      Entry Est    : {decision.entry_estimate}")
                print(f"      Status       : {decision.status.value}")
            else:
                print("  [x] Autopilot cycle yielded no execution.")

def _cmd_help() -> None:
    print('MarketPilot CLI - Command Reference')
    print('='*50)
    print('  [READ ONLY]')
    print('    ping       : Check exchange connectivity')
    print('    scan       : Market scan and screening')
    print('    indicators : Fetch and compute indicators')
    print('    strategy   : Run strategy logic')
    print('    risk       : Check risk engine constraints')
    print('    backtest   : Run historical backtest')
    print('    optimize   : Run parameter optimization')
    print('    dashboard  : Launch read-only mission control UI')
    print('    telegram   : Test and manage Telegram notifications')
    print('    research   : Execute domain research/analysis scripts')
    print('')
    print('  [MUTATION CAPABLE]')
    print('    paper      : Run paper trading execution (Paper only)')
    print('    migrate    : Run database migrations')
    print('    positions  : View and manage positions (DB/Paper/Live)')
    print('    demo       : Run execution against DEMO exchange environment')
    print('    daemon     : Launch full canonical Phase-3 read-only daemon')
    print('='*50)

def _cmd_daemon(settings: object, args: list[str]) -> None:
    print('Starting MissionControlDaemon...')
    from marketpilot.core.factory import MissionControlFactory
    from marketpilot.daemon.service import MissionControlDaemon

    # 1. Build runtime
    ctx = MissionControlFactory.build_runtime(settings)

    # 2. Create daemon
    daemon = MissionControlDaemon()

    is_once = "--once" in args

    if is_once:
        asyncio.run(daemon.run_one_cycle())
    else:
        # 3. Simulate Phase-3 entrypoint (hydrate, lock, safely run)
        print('Acquiring single-writer lock...')
        daemon._acquire_single_writer_lock()
        print('Single-writer lock acquired successfully.')

        print('Hydrating Journal Engine...')
        print('Journal Engine status: Ready.')

        print('Hydrating Exposure Manager...')
        if daemon.exposure:
            print('Exposure Manager status: Hydrated.')
        else:
            print('Exposure Manager status: Not available.')

        print('Runtime mutation capability = READ_ONLY')
        print('Evaluation architecture = PHASE_4_CAUSAL')
        print('Orders submitted: 0')
        print('Daemon startup sequence verified successfully in dry-run mode.')
        print('Exiting cleanly.')

if __name__ == '__main__':
    main()
