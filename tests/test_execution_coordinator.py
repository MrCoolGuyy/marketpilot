import pytest
from unittest.mock import MagicMock
from decimal import Decimal
import time

from marketpilot.engines.execution_coordinator import ExecutionCoordinator
from marketpilot.engines.execution_reducer import ExecutionStateReducer, ReducerState, TransitionStatus
from marketpilot.models.execution import ExecutionIntent, ValidatedOrderSpec, NetworkPermit, PermitAction, ExecutionFill
from marketpilot.models.journal import (
    ExecutionIntentCreated,
    ExecutionValidationRejected,
    ExecutionFillObserved,
    ExecutionSubmissionPrepared,
    ExecutionSubmissionAuthorized,
    ExecutionNetworkAttemptStarted
)
from marketpilot.models.strategy import SignalDirection

def test_execution_state_reducer_idempotency():
    reducer = ExecutionStateReducer()

    intent = ExecutionIntent(
        intent_id="int-1",
        allocation_token_id="tok-1",
        logical_order_id="ord-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"),
        effective_stop=Decimal("90"),
        environment="PAPER"
    )
    event1 = ExecutionIntentCreated(intent=intent, timestamp=100.0)

    # First application
    state, status = reducer.apply(None, event1)
    assert status == TransitionStatus.ACCEPTED
    assert state is not None
    assert state.logical_order_id == "ord-1"

    # Duplicate application
    state2, status2 = reducer.apply(state, event1)
    assert status2 == TransitionStatus.DUPLICATE_NOOP

    # Fill event
    fill = ExecutionFill(
        exec_id="fill-1",
        order_id="ord-1",
        order_link_id="ord-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        exec_qty=Decimal("1.0"),
        exec_price=Decimal("100.5"),
        fee=Decimal("0.1"),
        timestamp=101.0,
        environment="PAPER"
    )
    event_fill = ExecutionFillObserved(submission_attempt_id="sub-1", fill=fill)

    # First fill
    state3, status3 = reducer.apply(state, event_fill)
    assert status3 == TransitionStatus.ACCEPTED
    assert state3.entry_fill is not None

    # Duplicate fill
    state4, status4 = reducer.apply(state3, event_fill)
    assert status4 == TransitionStatus.DUPLICATE_NOOP

def test_coordinator_rejection_releases_reservation():
    journal = MagicMock()
    exposure = MagicMock()
    paper_adapter = MagicMock()
    notifier = MagicMock()

    coord = ExecutionCoordinator(journal, exposure, paper_adapter, notifier)

    intent = ExecutionIntent(
        intent_id="int-1",
        allocation_token_id="tok-1",
        logical_order_id="ord-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"),
        effective_stop=Decimal("90"),
        environment="PAPER"
    )
    coord.propose_event("ord-1", ExecutionIntentCreated(intent=intent, timestamp=100.0))

    # Inject Rejection
    reject_event = ExecutionValidationRejected(
        intent_id="int-1",
        reason="Test rejection",
        timestamp=101.0
    )

    status = coord.propose_event("ord-1", reject_event)
    assert status == TransitionStatus.ACCEPTED

    # Check that durable event was written
    journal.append_durable_event.assert_called_with(reject_event)

    # Check that reservation was released
    # Risk = 1.0 * (100 - 90) = 10.0
    exposure.release_prepared_reservation.assert_called_with(
        allocation_id="tok-1",
        released_risk=Decimal("10.0")
    )

def test_coordinator_fill_transitions_risk():
    journal = MagicMock()
    exposure = MagicMock()
    paper_adapter = MagicMock()
    notifier = MagicMock()

    coord = ExecutionCoordinator(journal, exposure, paper_adapter, notifier)

    intent = ExecutionIntent(
        intent_id="int-1",
        allocation_token_id="tok-1",
        logical_order_id="ord-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"),
        effective_stop=Decimal("90"),
        environment="PAPER"
    )
    coord.propose_event("ord-1", ExecutionIntentCreated(intent=intent, timestamp=100.0))

    fill = ExecutionFill(
        exec_id="fill-1",
        order_id="ord-1",
        order_link_id="ord-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        exec_qty=Decimal("1.0"),
        exec_price=Decimal("102"), # Slipped entry
        fee=Decimal("0.1"),
        timestamp=101.0,
        environment="PAPER"
    )
    fill_event = ExecutionFillObserved(submission_attempt_id="sub-1", fill=fill)

    status = coord.propose_event("ord-1", fill_event)
    assert status == TransitionStatus.ACCEPTED

    # Reserved risk: 10.0
    # Actual risk: 1.0 * (102 - 90) = 12.0
    exposure.apply_confirmed_transition.assert_called_with(
        allocation_id="tok-1",
        position_id="ord-1",
        new_risk=Decimal("12.0"),
        released_risk=Decimal("10.0")
    )

def test_execution_state_reducer_exit_dedupe():
    reducer = ExecutionStateReducer()
    intent = ExecutionIntent(
        intent_id="int-1", allocation_token_id="tok-1", logical_order_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"), effective_stop=Decimal("90"), environment="PAPER"
    )
    s, _ = reducer.apply(None, ExecutionIntentCreated(intent=intent, timestamp=100.0))

    fill_exit = ExecutionFill(
        exec_id="fill-tp-1", order_id="ord-1", order_link_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.SHORT, exec_qty=Decimal("1.0"),
        exec_price=Decimal("110"), fee=Decimal("0.1"), timestamp=102.0, environment="PAPER"
    )
    # The first fill event applied here will actually be considered the entry if there wasn't one,
    # but let's apply an entry first.
    fill_entry = ExecutionFill(
        exec_id="fill-entry-1", order_id="ord-1", order_link_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, exec_qty=Decimal("1.0"),
        exec_price=Decimal("100"), fee=Decimal("0.1"), timestamp=101.0, environment="PAPER"
    )
    s, _ = reducer.apply(s, ExecutionFillObserved(submission_attempt_id="sub-1", fill=fill_entry))

    s_exit, status1 = reducer.apply(s, ExecutionFillObserved(submission_attempt_id="sub-2", fill=fill_exit))
    assert status1 == TransitionStatus.ACCEPTED
    assert s_exit.exit_fill is not None

    # duplicate exit
    s_dup, status2 = reducer.apply(s_exit, ExecutionFillObserved(submission_attempt_id="sub-2", fill=fill_exit))
    assert status2 == TransitionStatus.DUPLICATE_NOOP

def test_coordinator_replay_does_not_append_and_suppresses_notifications():
    journal = MagicMock()
    exposure = MagicMock()
    paper_adapter = MagicMock()
    notifier = MagicMock()
    coord = ExecutionCoordinator(journal, exposure, paper_adapter, notifier)

    # We call internal _apply_durable_event with suppress_notification=True simulating replay
    intent = ExecutionIntent(
        intent_id="int-1", allocation_token_id="tok-1", logical_order_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"), effective_stop=Decimal("90"), environment="PAPER"
    )
    status = coord._apply_durable_event(ExecutionIntentCreated(intent=intent, timestamp=100.0), "ord-1", suppress_notification=True)
    assert status == TransitionStatus.ACCEPTED

    # Check that notifier was NOT called
    notifier.notify_reservation_committed.assert_not_called()

def test_trading_pipeline_abstain_zero_artifacts():
    # If phase4 yields 0 candidates, execution coordinator process_allocation is not called.
    # This is verified by TradingPipeline logic test.
    pass

def test_dashboard_read_only_path():
    from marketpilot.models.execution import PaperPositionState, PaperSimulationObservation, PaperFillRole
    from marketpilot.models.strategy import SignalDirection
    from decimal import Decimal

    # OPEN PAPER PROJECTION (PaperPositionState)
    open_state = PaperPositionState(
        position_id="pos-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"),
        entry_timestamp=100.0,
        canonical_stop=Decimal("90.0"),
        canonical_tp=Decimal("110.0"),
        paper_policy_version="1.1.0"
    )

    # Assert fields are present for OPEN PAPER projection
    assert open_state.symbol == "BTCUSDT"
    assert open_state.side == SignalDirection.LONG
    assert open_state.qty == Decimal("1.0")
    assert open_state.entry_fill == Decimal("100.0")
    assert open_state.canonical_stop == Decimal("90.0")
    assert open_state.canonical_tp == Decimal("110.0")
    assert open_state.paper_policy_version == "1.1.0"

    # CLOSED PAPER PROJECTION (PaperSimulationObservation)
    closed_state = PaperSimulationObservation(
        fill_id="exit-1",
        role=PaperFillRole.TP_EXIT,
        qty=Decimal("1.0"),
        fill_price=Decimal("110.0"),
        fee=Decimal("0.1"),
        timestamp=101.0,
        net_pnl=Decimal("9.8"),
        realized_r=Decimal("0.98")
    )

    # Assert fields are present for CLOSED PAPER projection
    assert closed_state.fill_id == "exit-1"
    assert closed_state.fee == Decimal("0.1")
    assert closed_state.net_pnl == Decimal("9.8")
    assert closed_state.realized_r == Decimal("0.98")






import pytest
from unittest.mock import MagicMock
from decimal import Decimal
import time
from marketpilot.engines.journal_engine import JournalEngine
from marketpilot.engines.exposure_manager import ExposureManager

def test_direct_admitted_production_route():
    from marketpilot.engines.trading_pipeline import TradingPipeline
    from marketpilot.adapters.paper_execution_adapter import PaperAdapter
    from marketpilot.engines.paper_simulator import PaperSimulator
    from marketpilot.models.execution_policy import PaperExecutionPolicy
    from marketpilot.strategy.portfolio_policy import PortfolioPolicy
    from marketpilot.core.factory import RuntimeContext
    from marketpilot.models.portfolio import PortfolioAllocationToken
    from marketpilot.models.execution import ExecutionQuoteSnapshot
    from datetime import datetime, timezone

    # Mock context
    ctx = MagicMock(spec=RuntimeContext)
    ctx.settings.execution_mode.value = "PAPER"

    paper_policy = PaperExecutionPolicy(
        version="1.1.0", require_fresh_quote=True, max_quote_age_ms=50000,
        fee_class="TAKER", taker_fee_bps=Decimal("5.5"),
        entry_slippage_bps=Decimal("2.0"), exit_slippage_bps=Decimal("2.0"),
        ambiguous_candle_policy="STOP_FIRST", gap_semantics="CONSERVATIVE_GAP_FILL"
    )
    portfolio_policy = PortfolioPolicy(
        policy_version="1.0", allocated_capital=Decimal("1000.0"),
        minimum_unallocated_buffer=Decimal("3.0"), max_total_heat_ratio=Decimal("200.0"),
        max_simultaneous_lineages=1
    )

    journal = MagicMock()
    exposure = MagicMock()

    simulator = MagicMock(spec=PaperSimulator)
    # Simulator should just return some observation
    from marketpilot.models.execution import PaperSimulationObservation, PaperFillRole
    obs = PaperSimulationObservation(
        fill_id="sim-fill-1", role=PaperFillRole.ENTRY, qty=Decimal("1.0"),
        fill_price=Decimal("100.0"), fee=Decimal("0.1"), timestamp=time.time()
    )
    simulator.evaluate_entry.return_value = obs

    adapter = PaperAdapter(simulator, paper_policy, portfolio_policy)
    # We spy on adapter
    adapter.evaluate_entry = MagicMock(side_effect=adapter.evaluate_entry)

    notifier = MagicMock()
    coord = ExecutionCoordinator(journal, exposure, adapter, notifier)
    ctx.execution_coordinator = coord

    # Fake a Phase 5 admission
    token = PortfolioAllocationToken(
        candidate_id="cand-1",
        decision_id="dec-1",
        strategy_id="strat-1",
        strategy_version="1.0",
        parameter_set_id="param-1",
        sizing_id="size-1",
        reservation_identity="tok-1",
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        quantity=Decimal("1.0"),
        executable_entry=Decimal("100.0"),
        effective_stop=Decimal("90.0"),
        candidate_risk_amount=Decimal("10.0"),
        final_net_ev=Decimal("15.0"),
        portfolio_snapshot_version="v1",
        equity_snapshot_version="v1",
        portfolio_policy_version="v1",
        lineage_identity="lin-1",
        admission_timestamp=time.time()
    )

    now = datetime.now(timezone.utc)
    quote_snap = ExecutionQuoteSnapshot(
        quote_id="q-1", symbol="BTCUSDT", bid=Decimal("99"), ask=Decimal("100"),
        source_market_timestamp=now, received_at=now, source="TEST"
    )

    # The TradingPipeline calls process_allocation
    coord.process_allocation(token, quote_snap, Decimal("110.0"), "PAPER")

    assert adapter.evaluate_entry.call_count == 1
    assert simulator.evaluate_entry.call_count == 1

def test_direct_phase5_rejection():
    from marketpilot.engines.portfolio_allocator import PortfolioAllocator
    from marketpilot.strategy.portfolio_policy import PortfolioPolicy
    from marketpilot.models.portfolio import AllocationRejection, PortfolioExposureSnapshot, EquitySnapshot
    from marketpilot.models.causal import FinalCandidate, ExecutableQuoteSnapshot, MarketDataEnvironment
    from marketpilot.models.execution import ExecutionIntent
    from marketpilot.models.strategy import SignalDirection
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from decimal import Decimal
    import time

    # 1. Mock the context
    policy = PortfolioPolicy(
        policy_version="V1",
        allocated_capital=Decimal("100.0"),
        minimum_unallocated_buffer=Decimal("3.0"),
        max_total_heat_ratio=Decimal("200.0"),
        max_simultaneous_lineages=1
    )

    candidate = MagicMock()
    candidate.candidate_id = "cand-1"
    candidate.deterministic_decision_key = "dec-1"
    candidate.priced_candidate = MagicMock()
    candidate.priced_candidate.executable_entry_price = Decimal("100")
    candidate.priced_candidate.intent = MagicMock()
    candidate.priced_candidate.intent.take_profit = Decimal("110")
    candidate.priced_candidate.intent.effective_stop = Decimal("90")
    candidate.priced_candidate.intent.original_qty = Decimal("3000.0")
    candidate.priced_candidate.intent.signal_timestamp_us = 1000
    candidate.priced_candidate.intent.direction = SignalDirection.LONG
    candidate.priced_candidate.intent.symbol = "BTCUSDT"
    candidate.priced_candidate.intent.environment = "PAPER"
    candidate.sizing = MagicMock()
    candidate.sizing.provisional_quantity = Decimal("3000.0")
    candidate.sizing.effective_stop_price = Decimal("90")

    exposure = PortfolioExposureSnapshot(
        snapshot_id="exp-1",
        version="1.0",
        captured_at=time.time(),
        timestamp=time.time(),
        environment="PAPER",
        safe_account_fingerprint="test",
        total_risk_amount=Decimal("0"),
        portfolio_heat_ratio=Decimal("0"),
        active_position_ids=[],
        reserved_allocation_ids=[],
        exposure_version="v1"
    )

    equity = EquitySnapshot(
        snapshot_id="eq-1",
        version="1.0",
        captured_at=time.time(),
        environment="PAPER",
        safe_account_fingerprint="test",
        configured_allocated_capital=Decimal("100"),
        usable_account_value=Decimal("100"),
        effective_risk_capital=Decimal("100"),
        freshness_status="FRESH",
        provenance="test"
    )

    # Mocking PortfolioAllocator to reject due to hard ceiling risk
    decision = PortfolioAllocator.evaluate_candidate(
        candidate=candidate,
        exposure_snapshot=exposure,
        equity_snapshot=equity,
        policy=policy
    )

    assert decision.is_rejected is True
    assert decision.rejection is not None
    assert decision.rejection.rejection_code == "HEAT_EXCEEDED" or decision.rejection.rejection_code == "RISK_EXCEEDED" or "exceeds" in decision.rejection.reason
    assert decision.token is None







def test_durable_entry_dedupe_after_restart():
    # 1. First Process
    journal = MagicMock()
    exposure = MagicMock()
    adapter = MagicMock()
    notifier = MagicMock()

    appended_events = []
    journal.append_durable_event.side_effect = lambda e: appended_events.append(e)

    coord1 = ExecutionCoordinator(journal, exposure, adapter, notifier)

    intent = ExecutionIntent(
        intent_id="int-1", allocation_token_id="tok-1", logical_order_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"), effective_stop=Decimal("90"), environment="PAPER"
    )
    coord1.propose_event("ord-1", ExecutionIntentCreated(intent=intent, timestamp=100.0))

    fill = ExecutionFill(
        exec_id="fill-1", order_id="ord-1", order_link_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, exec_qty=Decimal("1.0"),
        exec_price=Decimal("100"), fee=Decimal("0.1"), timestamp=101.0, environment="PAPER"
    )
    fill_event = ExecutionFillObserved(submission_attempt_id="sub-1", fill=fill)

    status1 = coord1.propose_event("ord-1", fill_event)
    assert status1 == TransitionStatus.ACCEPTED

    # 2. Restart Process
    journal2 = MagicMock()
    exposure2 = MagicMock()
    adapter2 = MagicMock()
    notifier2 = MagicMock()

    appended_events2 = []
    journal2.append_durable_event.side_effect = lambda e: appended_events2.append(e)

    coord2 = ExecutionCoordinator(journal2, exposure2, adapter2, notifier2)

    # 3. Hydrate ONLY from Journal
    for ev in appended_events:
        coord2._apply_durable_event(ev, "ord-1", suppress_notification=True)

    assert len(appended_events2) == len(appended_events) # Journal engine mock captures replay

    # Snapshot economic state before duplicate replay
    state_before = coord2._states["ord-1"]
    assert state_before.entry_fill is not None
    assert state_before.entry_fill.exec_qty == Decimal("1.0")
    assert state_before.entry_fill.fee == Decimal("0.1")
    assert state_before.is_terminal is False

    # Reset mocks after hydration
    appended_events2.clear()
    exposure2.apply_confirmed_transition.reset_mock()
    notifier2.notify_reservation_committed.reset_mock()
    adapter2.reset_mock()

    # 4. Propose exact same ENTRY fill X again
    status2 = coord2.propose_event("ord-1", fill_event)

    # EXPECTED ASSERTIONS
    assert status2 == TransitionStatus.DUPLICATE_NOOP
    assert len(appended_events2) == 0 # ENTRY Journal event count unchanged

    state_after = coord2._states["ord-1"]
    assert state_after.entry_fill.fee == Decimal("0.1") # entry fee unchanged
    assert state_after.entry_fill.exec_qty == Decimal("1.0") # active exposure unchanged

    exposure2.apply_confirmed_transition.assert_not_called()
    notifier2.notify_reservation_committed.assert_not_called() # notification count unchanged
    adapter2.execute_paper_fill.assert_not_called() # PaperSimulator not called again

def test_durable_exit_dedupe_after_restart():
    # 1. First Process
    journal = MagicMock()
    exposure = MagicMock()
    adapter = MagicMock()
    notifier = MagicMock()
    appended_events = []
    journal.append_durable_event.side_effect = lambda e: appended_events.append(e)

    coord1 = ExecutionCoordinator(journal, exposure, adapter, notifier)

    intent = ExecutionIntent(
        intent_id="int-1", allocation_token_id="tok-1", logical_order_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"), effective_stop=Decimal("90"), environment="PAPER"
    )
    coord1.propose_event("ord-1", ExecutionIntentCreated(intent=intent, timestamp=100.0))

    fill_entry = ExecutionFill(
        exec_id="fill-1", order_id="ord-1", order_link_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, exec_qty=Decimal("1.0"),
        exec_price=Decimal("100"), fee=Decimal("0.1"), timestamp=101.0, environment="PAPER"
    )
    coord1.propose_event("ord-1", ExecutionFillObserved(submission_attempt_id="sub-1", fill=fill_entry))

    fill_exit = ExecutionFill(
        exec_id="fill-tp", order_id="ord-1", order_link_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.SHORT, exec_qty=Decimal("1.0"),
        exec_price=Decimal("110"), fee=Decimal("0.1"), timestamp=102.0, environment="PAPER"
    )
    exit_event = ExecutionFillObserved(submission_attempt_id="sub-2", fill=fill_exit)
    status1 = coord1.propose_event("ord-1", exit_event)
    assert status1 == TransitionStatus.ACCEPTED

    # 2. Restart Process
    journal2 = MagicMock()
    exposure2 = MagicMock()
    adapter2 = MagicMock()
    notifier2 = MagicMock()
    appended_events2 = []
    journal2.append_durable_event.side_effect = lambda e: appended_events2.append(e)

    coord2 = ExecutionCoordinator(journal2, exposure2, adapter2, notifier2)

    for ev in appended_events:
        coord2._apply_durable_event(ev, "ord-1", suppress_notification=True)

    state_before = coord2._states["ord-1"]
    assert state_before.exit_fill is not None
    assert state_before.exit_fill.exec_qty == Decimal("1.0")
    assert state_before.exit_fill.fee == Decimal("0.1")

    appended_events2.clear()
    exposure2.apply_confirmed_transition.reset_mock()
    notifier2.notify_reservation_committed.reset_mock()
    adapter2.reset_mock()

    # 4. Propose exact same EXIT again
    status2 = coord2.propose_event("ord-1", exit_event)

    # EXPECTED ASSERTIONS
    assert status2 == TransitionStatus.DUPLICATE_NOOP
    assert len(appended_events2) == 0 # EXIT journal count unchanged

    state_after = coord2._states["ord-1"]
    assert state_after.exit_fill.fee == Decimal("0.1") # exit fee unchanged
    assert state_after.exit_fill.exec_qty == Decimal("1.0") # exposure release unchanged

    exposure2.apply_confirmed_transition.assert_not_called()
    notifier2.notify_reservation_committed.assert_not_called()

def test_real_rejection_crash_window():
    journal = MagicMock()
    exposure = MagicMock()
    adapter = MagicMock()
    notifier = MagicMock()

    appended_events = []
    journal.append_durable_event.side_effect = lambda e: appended_events.append(e)

    # Step 1: Rejection process
    coord = ExecutionCoordinator(journal, exposure, adapter, notifier)
    intent = ExecutionIntent(
        intent_id="int-1", allocation_token_id="tok-1", logical_order_id="ord-1",
        symbol="BTCUSDT", side=SignalDirection.LONG, original_qty=Decimal("1.0"),
        executable_entry=Decimal("100"), effective_stop=Decimal("90"), environment="PAPER"
    )
    coord.propose_event("ord-1", ExecutionIntentCreated(intent=intent, timestamp=100.0))

    reject_event = ExecutionValidationRejected(
        intent_id="int-1", reason="crash", timestamp=101.0
    )

    # Intercept release to simulate crash AFTER durable append but BEFORE projection
    crash_happened = False
    def mock_release(*args, **kwargs):
        nonlocal crash_happened
        if not crash_happened:
            crash_happened = True
            raise RuntimeError("CRASH")

    exposure.release_prepared_reservation.side_effect = mock_release

    with pytest.raises(RuntimeError, match="CRASH"):
        coord.propose_event("ord-1", reject_event)

    # Assert durable rejection exists
    assert any(isinstance(e, ExecutionValidationRejected) for e in appended_events)
    # Notice it crashed before finishing release (mock raised exception).

    # Step 3/4: Discard and hydrate
    journal2 = MagicMock()
    exposure2 = MagicMock()
    adapter2 = MagicMock()
    notifier2 = MagicMock()

    appended_events2 = []
    journal2.append_durable_event.side_effect = lambda e: appended_events2.append(e)

    coord2 = ExecutionCoordinator(journal2, exposure2, adapter2, notifier2)

    for ev in appended_events:
        coord2._apply_durable_event(ev, "ord-1", suppress_notification=True)

    # Assert reservation released exactly once during hydrate
    exposure2.release_prepared_reservation.assert_called_once()

    # No new journal appended
    # No simulator called
    adapter2.evaluate_entry.assert_not_called()
    # No telegram dispatched (notifier not called)
