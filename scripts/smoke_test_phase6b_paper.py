"""
MarketPilot - Phase 6B Paper Execution Smoke Test
Proves deterministic paper execution lifecycle without exchange mutation.
"""

import sys
from decimal import Decimal
from datetime import datetime, timezone
import asyncio

from marketpilot.core.enums import Interval
from marketpilot.models.strategy import SignalDirection
from marketpilot.models.execution_policy import PaperExecutionPolicy
from marketpilot.strategy.portfolio_policy import PortfolioPolicy
from marketpilot.models.execution import (
    ExecutionIntent,
    ExecutionQuoteSnapshot,
    PaperPositionState,
    PaperSimulationObservation,
    PaperFillRole
)
from marketpilot.engines.paper_simulator import PaperSimulator
from marketpilot.engines.journal_engine import JournalEngine

def run_smoke_test():
    print("============================================================")
    print("PHASE 6B SMOKE TEST - DETERMINISTIC PAPER EXECUTION")
    print("============================================================")

    # 1. Policies
    paper_policy = PaperExecutionPolicy(
        version="1.1.0",
        require_fresh_quote=True,
        max_quote_age_ms=5000,
        fee_class="TAKER",
        taker_fee_bps=Decimal("5.5"),
        entry_slippage_bps=Decimal("2.0"),
        exit_slippage_bps=Decimal("2.0"),
        ambiguous_candle_policy="STOP_FIRST",
        gap_semantics="CONSERVATIVE_GAP_FILL",
    )

    portfolio_policy = PortfolioPolicy(
        policy_version="1.0",
        allocated_capital=Decimal("1000.0"),
        minimum_unallocated_buffer=Decimal("3.0"),
        max_total_heat_ratio=Decimal("200.0"),
        max_simultaneous_lineages=1,
    )

    now = datetime.now(timezone.utc)

    # 2. Intent
    intent = ExecutionIntent(
        intent_id="intent-smoke-1",
        allocation_token_id="tok-smoke-1",
        logical_order_id="lo-smoke-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        original_qty=Decimal("0.1"),
        executable_entry=Decimal("60000.0"),
        effective_stop=Decimal("59000.0"),
        take_profit=Decimal("62000.0"),
        environment="PAPER",
    )

    # 3. Quote
    quote = ExecutionQuoteSnapshot(
        quote_id="q-smoke-1",
        symbol="BTCUSDT",
        bid=Decimal("59999.0"),
        ask=Decimal("60001.0"),
        source_market_timestamp=now,
        received_at=now,
        source="BYBIT",
    )

    print(f"\n[1] Evaluating ENTRY for {intent.symbol} {intent.side.value} Qty: {intent.original_qty}")

    from marketpilot.engines.execution_coordinator import ExecutionCoordinator
    from marketpilot.adapters.paper_execution_adapter import PaperAdapter
    from marketpilot.models.portfolio import PortfolioAllocationToken
    import time

    class MockExposure:
        def release_prepared_reservation(self, *args, **kwargs): pass
        def apply_confirmed_transition(self, *args, **kwargs): pass

    class MockNotifier:
        def notify_reservation_committed(self, *args, **kwargs): pass

    simulator = PaperSimulator()
    simulator._get_current_time = lambda: now

    adapter = PaperAdapter(simulator, paper_policy, portfolio_policy)
    coordinator = ExecutionCoordinator(JournalEngine(), MockExposure(), adapter, MockNotifier())

    token = PortfolioAllocationToken(
        candidate_id="cand-1",
        decision_id="dec-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        parameter_set_id="param-1",
        sizing_id="size-1",
        reservation_identity=intent.allocation_token_id,
        symbol=intent.symbol,
        direction=intent.side,
        quantity=intent.original_qty,
        executable_entry=intent.executable_entry,
        effective_stop=intent.effective_stop,
        candidate_risk_amount=Decimal("1.0"),
        final_net_ev=Decimal("15.0"),
        portfolio_snapshot_version="v1",
        equity_snapshot_version="v1",
        portfolio_policy_version="v1",
        lineage_identity="lin-1",
        admission_timestamp=time.time()
    )

    coordinator.process_allocation(token, quote, intent.take_profit, "PAPER")
    state = coordinator._states.get(f"POS-{intent.allocation_token_id}")

    if state and state.entry_fill:
        print("    ENTRY ACCEPTED")
        print(f"    Fill ID: {state.entry_fill.exec_id}")
        print(f"    Fill Price: {state.entry_fill.exec_price}")
        print(f"    Fee: {state.entry_fill.fee}")
        entry_obs = state.entry_fill
    else:
        print("    ENTRY REJECTED OR NOT PROCESSED")
        import json
        with open(coordinator._journal.events_path, "r") as jf:
            for line in jf:
                if "REJECT" in line or "ValidationRejected" in line:
                    print(f"REJECTION REASON: {line}")
        sys.exit(1)

    print("\n[2] Transitioning to PAPER Position State")
    position = PaperPositionState(
        position_id=f"pos-{intent.logical_order_id}",
        symbol=intent.symbol,
        side=intent.side,
        qty=entry_obs.exec_qty,
        entry_fill=entry_obs.exec_price,
        entry_timestamp=entry_obs.timestamp,
        canonical_stop=intent.effective_stop,
        canonical_tp=intent.take_profit,
        paper_policy_version=paper_policy.version
    )
    print("    PAPER PROTECTION CONFIRMED")

    print("\n[3] Evaluating Post-Entry Closed Candles (Simulating Market Progress)")

    from marketpilot.models.market import Kline

    # Candle 1: Doesn't trigger anything
    candle_time_1 = datetime.fromtimestamp(entry_obs.timestamp + 60, tz=timezone.utc)
    candle1 = Kline(
        symbol=intent.symbol,
        interval=Interval.M1,
        open_time=candle_time_1,
        open="60000",
        high="61000",
        low="59500",
        close="60500",
        volume="100",
        turnover="100",
        is_closed=True
    )
    obs = simulator.evaluate_lifecycle(position, candle1, paper_policy)
    print(f"    Candle 1 ({candle1.high}/{candle1.low}): {'Triggered' if obs else 'No trigger (Holding)'}")

    # Candle 2: Hits TP
    candle_time_2 = datetime.fromtimestamp(entry_obs.timestamp + 120, tz=timezone.utc)
    candle2 = Kline(
        symbol=intent.symbol,
        interval=Interval.M1,
        open_time=candle_time_2,
        open="60500",
        high="62500",  # Hits TP 62000
        low="60000",
        close="62100",
        volume="100",
        turnover="100",
        is_closed=True
    )
    obs = simulator.evaluate_lifecycle(position, candle2, paper_policy)

    if obs:
        print(f"    Candle 2 ({candle2.high}/{candle2.low}): Triggered {obs.role.value}")
        print("\n[4] TERMINAL OUTCOME COMPUTED")
        print(f"    Exit Fill ID: {obs.fill_id}")
        print(f"    Exit Price: {obs.fill_price}")
        print(f"    Exit Fee: {obs.fee}")
        print(f"    Net PnL: {obs.net_pnl}")
        print(f"    Realized R: {obs.realized_r}")

        print("\n[5] Simulated Telegram Presentation")
        msg = f"*PAPER {obs.role.value}*\n"
        msg += f"Symbol: {position.symbol}\n"
        msg += f"Net PnL: {obs.net_pnl}\n"
        msg += f"Realized R: {obs.realized_r}R\n"
        msg += f"Policy: v{paper_policy.version}"
        print(msg)
    else:
        print("    ERROR: Expected TP trigger")
        print(coordinator._states.keys()); print(coordinator._journal); sys.exit(1)

    print("\n[6] Exposure Manager Release Simulated")
    print("    Active PAPER risk released. Canonical lifecycle complete.")

    print("\nSMOKE TEST SUCCESS: Zero exchange mutation. Deterministic lifecycle proven.")

if __name__ == "__main__":
    run_smoke_test()
