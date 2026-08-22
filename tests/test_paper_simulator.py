"""
Tests for the deterministic PaperSimulator domain engine.
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from marketpilot.engines.paper_simulator import PaperSimulator, PaperSimulationRejected
from marketpilot.models.execution import (
    ExecutionIntent,
    ExecutionQuoteSnapshot,
    PaperPositionState,
    PaperFillRole,
)
from marketpilot.models.execution_policy import PaperExecutionPolicy
from marketpilot.models.strategy import SignalDirection
from marketpilot.strategy.portfolio_policy import PortfolioPolicy
from marketpilot.models.market import Kline


@pytest.fixture
def base_paper_policy():
    return PaperExecutionPolicy(
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


@pytest.fixture
def base_portfolio_policy():
    return PortfolioPolicy(
        policy_version="1.0",
        allocated_capital=Decimal("1000.0"),
        minimum_unallocated_buffer=Decimal("3.0"),
        max_total_heat_ratio=Decimal("100.0"), # Allow up to 10000% for testing values
        max_simultaneous_lineages=1,
    )


@pytest.fixture
def sample_intent_long():
    return ExecutionIntent(
        intent_id="intent-1",
        allocation_token_id="tok-1",
        logical_order_id="lo-1",
        symbol="BTCUSDT",
        side=SignalDirection.LONG,
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100.0"),
        effective_stop=Decimal("99.0"),
        take_profit=Decimal("105.0"),
        environment="PAPER",
    )


@pytest.fixture
def sample_intent_short():
    return ExecutionIntent(
        intent_id="intent-2",
        allocation_token_id="tok-2",
        logical_order_id="lo-2",
        symbol="BTCUSDT",
        side=SignalDirection.SHORT,
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100.0"),
        effective_stop=Decimal("101.0"),
        take_profit=Decimal("95.0"),
        environment="PAPER",
    )


@pytest.fixture
def fresh_quote(monkeypatch):
    now = datetime.now(timezone.utc)
    # Mock current time in simulator to match 'now'
    monkeypatch.setattr(PaperSimulator, "_get_current_time", lambda self: now)

    return ExecutionQuoteSnapshot(
        quote_id="q-1",
        symbol="BTCUSDT",
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        source_market_timestamp=now,
        received_at=now,
        source="BYBIT",
    )


def test_stale_quote_rejected(base_paper_policy, base_portfolio_policy, sample_intent_long, monkeypatch):
    simulator = PaperSimulator()
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(PaperSimulator, "_get_current_time", lambda self: now)

    stale_quote = ExecutionQuoteSnapshot(
        quote_id="q-stale",
        symbol="BTCUSDT",
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        source_market_timestamp=now - timedelta(seconds=10),
        received_at=now - timedelta(seconds=10),
        source="BYBIT",
    )

    with pytest.raises(PaperSimulationRejected, match="Quote stale"):
        simulator.evaluate_entry(
            intent=sample_intent_long,
            quote=stale_quote,
            paper_policy=base_paper_policy,
            portfolio_policy=base_portfolio_policy,
            current_portfolio_heat=Decimal("0"),
            allocation_reserved_risk=Decimal("0"),
            max_allowed_risk=Decimal("5.0"),
        )


def test_invalid_bid_ask_rejected(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()
    invalid_quote = fresh_quote.model_copy(update={"bid": Decimal("100.1"), "ask": Decimal("99.9")})

    with pytest.raises(PaperSimulationRejected, match="Invalid quote bid/ask spread"):
        simulator.evaluate_entry(
            intent=sample_intent_long,
            quote=invalid_quote,
            paper_policy=base_paper_policy,
            portfolio_policy=base_portfolio_policy,
            current_portfolio_heat=Decimal("0"),
            allocation_reserved_risk=Decimal("0"),
            max_allowed_risk=Decimal("5.0"),
        )


def test_quote_symbol_mismatch(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()
    mismatch_quote = fresh_quote.model_copy(update={"symbol": "ETHUSDT"})

    with pytest.raises(PaperSimulationRejected, match="Quote symbol mismatch"):
        simulator.evaluate_entry(
            intent=sample_intent_long,
            quote=mismatch_quote,
            paper_policy=base_paper_policy,
            portfolio_policy=base_portfolio_policy,
            current_portfolio_heat=Decimal("0"),
            allocation_reserved_risk=Decimal("0"),
            max_allowed_risk=Decimal("5.0"),
        )


def test_paper_buy_fill_ask_basis_slippage(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()

    obs = simulator.evaluate_entry(
        intent=sample_intent_long,
        quote=fresh_quote,
        paper_policy=base_paper_policy,
        portfolio_policy=base_portfolio_policy,
        current_portfolio_heat=Decimal("0"),
        allocation_reserved_risk=Decimal("0"),
        max_allowed_risk=Decimal("5.0"),
    )

    # Base is ask (100.1)
    # slippage 2.0 bps = 0.0002
    # fill = 100.1 * 1.0002 = 100.12002
    expected_fill = Decimal("100.1") * Decimal("1.0002")
    assert obs.fill_price == expected_fill
    assert obs.role == PaperFillRole.ENTRY

    expected_fee = abs(Decimal("1.0") * expected_fill) * (Decimal("5.5") / Decimal("10000"))
    assert obs.fee == expected_fee


def test_paper_sell_fill_bid_basis_slippage(base_paper_policy, base_portfolio_policy, sample_intent_short, fresh_quote):
    simulator = PaperSimulator()

    obs = simulator.evaluate_entry(
        intent=sample_intent_short,
        quote=fresh_quote,
        paper_policy=base_paper_policy,
        portfolio_policy=base_portfolio_policy,
        current_portfolio_heat=Decimal("0"),
        allocation_reserved_risk=Decimal("0"),
        max_allowed_risk=Decimal("5.0"),
    )

    # Base is bid (99.9)
    # slippage 2.0 bps = 0.0002
    # fill = 99.9 * 0.9998 = 99.88002
    expected_fill = Decimal("99.9") * Decimal("0.9998")
    assert obs.fill_price == expected_fill
    assert obs.role == PaperFillRole.ENTRY

    expected_fee = abs(Decimal("1.0") * expected_fill) * (Decimal("5.5") / Decimal("10000"))
    assert obs.fee == expected_fee


def test_paper_requires_canonical_stops(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()

    bad_intent = sample_intent_long.model_copy(update={"take_profit": None})

    with pytest.raises(PaperSimulationRejected, match="Canonical TP is required"):
        simulator.evaluate_entry(
            intent=bad_intent,
            quote=fresh_quote,
            paper_policy=base_paper_policy,
            portfolio_policy=base_portfolio_policy,
            current_portfolio_heat=Decimal("0"),
            allocation_reserved_risk=Decimal("0"),
            max_allowed_risk=Decimal("5.0"),
        )


def test_long_entry_semantic_collapse(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()
    # Slippage so large it pushes entry above TP
    bad_policy = base_paper_policy.model_copy(update={"entry_slippage_bps": Decimal("50000.0")}) # 500%

    with pytest.raises(PaperSimulationRejected, match="collapsed LONG TP/SL relationship"):
        simulator.evaluate_entry(
            intent=sample_intent_long,
            quote=fresh_quote,
            paper_policy=bad_policy,
            portfolio_policy=base_portfolio_policy,
            current_portfolio_heat=Decimal("0"),
            allocation_reserved_risk=Decimal("0"),
            max_allowed_risk=Decimal("9999.0"),
        )


def test_prospective_actual_risk_hard_ceiling_rejection(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()

    # Hard max allowed risk is 1.0, but entry will have risk = (100.12 - 99.0) = 1.12
    with pytest.raises(PaperSimulationRejected, match="Prospective actual risk exceeds hard policy ceiling"):
        simulator.evaluate_entry(
            intent=sample_intent_long,
            quote=fresh_quote,
            paper_policy=base_paper_policy,
            portfolio_policy=base_portfolio_policy,
            current_portfolio_heat=Decimal("0"),
            allocation_reserved_risk=Decimal("0"),
            max_allowed_risk=Decimal("1.0"),
        )


def test_prospective_portfolio_heat_rejection(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()
    # current heat = 0.015, max = 0.02
    # We replace reservation 0.005 with actual ~0.0112 (from above)
    # Total heat = 0.015 - 0.005 + 0.0112 = 0.0212 > 0.02

    strict_policy = base_portfolio_policy.model_copy(update={"max_total_heat_ratio": Decimal("0.02")})

    with pytest.raises(PaperSimulationRejected, match="Prospective portfolio heat breach"):
        simulator.evaluate_entry(
            intent=sample_intent_long,
            quote=fresh_quote,
            paper_policy=base_paper_policy,
            portfolio_policy=strict_policy,
            current_portfolio_heat=Decimal("0.015"),
            allocation_reserved_risk=Decimal("0.005"),
            max_allowed_risk=Decimal("5.0"),
        )


def test_reservation_risk_replaced_not_double_counted(base_paper_policy, base_portfolio_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()
    # actual risk is ~1.12002
    # current heat = 1.13, max = 1.13
    # We replace reservation 1.121 with actual ~1.12002
    # Total heat = 1.13 - 1.121 + 1.12002 = 1.12902 <= 1.13
    # This proves it's replacement, NOT double counting (otherwise it would be 1.13 + 1.12002 = 2.25002 > 1.13)

    strict_policy = base_portfolio_policy.model_copy(update={"max_total_heat_ratio": Decimal("1.13")})

    obs = simulator.evaluate_entry(
        intent=sample_intent_long,
        quote=fresh_quote,
        paper_policy=base_paper_policy,
        portfolio_policy=strict_policy,
        current_portfolio_heat=Decimal("1.13"),
        allocation_reserved_risk=Decimal("1.121"),
        max_allowed_risk=Decimal("5.0"),
    )
    assert obs.role == PaperFillRole.ENTRY


# Lifecycle Tests
def test_overlapping_candle_ignored(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    # Overlapping: opens before 1000.0, closes after
    candle = Kline(open_time=datetime.fromtimestamp(999.0, tz=timezone.utc), open="100", high="150", low="50", close="100", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)
    assert obs is None


def test_unclosed_candle_rejected(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="100", high="150", low="50", close="100", volume="100", is_closed=False, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)
    assert obs is None


def test_tp_only_long(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="100", high="120", low="95", close="100", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    assert obs.role == PaperFillRole.TP_EXIT

    # TP Trigger base = 110.0
    # slippage = 2 bps
    # fill = 110.0 * 0.9998 = 109.978
    expected_fill = Decimal("110.0") * Decimal("0.9998")
    assert obs.fill_price == expected_fill
    assert obs.net_pnl is not None
    assert obs.realized_r is not None


def test_sl_only_short(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.SHORT, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("110.0"), canonical_tp=Decimal("90.0"), paper_policy_version="1.1"
    )

    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="100", high="120", low="95", close="100", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    assert obs.role == PaperFillRole.SL_EXIT

    # Short SL trigger base = max(110.0, 100.0) = 110.0
    # slippage = 2 bps (adverse)
    # fill = 110.0 * 1.0002 = 110.022
    expected_fill = Decimal("110.0") * Decimal("1.0002")
    assert obs.fill_price == expected_fill


def test_both_trigger_stop_first(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="100", high="120", low="80", close="100", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    assert obs.role == PaperFillRole.SL_EXIT # STOP_FIRST


def test_long_sl_gap_down(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    # Candle opens below SL (85.0)
    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="85.0", high="86", low="80", close="82", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    assert obs.role == PaperFillRole.SL_EXIT
    # Base = min(90.0, 85.0) = 85.0
    # fill = 85.0 * 0.9998 = 84.983
    expected_fill = Decimal("85.0") * Decimal("0.9998")
    assert obs.fill_price == expected_fill


def test_short_sl_gap_up(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.SHORT, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("110.0"), canonical_tp=Decimal("90.0"), paper_policy_version="1.1"
    )

    # Candle opens above SL (115.0)
    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="115.0", high="120", low="112", close="118", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    assert obs.role == PaperFillRole.SL_EXIT
    # Base = max(110.0, 115.0) = 115.0
    # fill = 115.0 * 1.0002 = 115.023
    expected_fill = Decimal("115.0") * Decimal("1.0002")
    assert obs.fill_price == expected_fill


def test_long_tp_favorable_gap_no_bonus(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    # Candle opens above TP (115.0)
    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="115.0", high="120", low="112", close="118", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    assert obs.role == PaperFillRole.TP_EXIT
    # Base = 110.0 (No bonus)
    # fill = 110.0 * 0.9998 = 109.978
    expected_fill = Decimal("110.0") * Decimal("0.9998")
    assert obs.fill_price == expected_fill


def test_canonical_realized_r(base_paper_policy):
    simulator = PaperSimulator()
    position = PaperPositionState(
        position_id="p-1", symbol="BTC", side=SignalDirection.LONG, qty=Decimal("1.0"),
        entry_fill=Decimal("100.0"), entry_timestamp=1000.0, canonical_stop=Decimal("90.0"), canonical_tp=Decimal("110.0"), paper_policy_version="1.1"
    )

    # Trigger TP
    candle = Kline(open_time=datetime.fromtimestamp(1001.0, tz=timezone.utc), open="100", high="120", low="95", close="100", volume="100", is_closed=True, symbol="BTCUSDT", interval="1", turnover="100")
    obs = simulator.evaluate_lifecycle(position, candle, base_paper_policy)

    assert obs is not None
    # Actual initial risk = qty * abs(100.0 - 90.0) = 10.0
    # Exit fill = 110 * 0.9998 = 109.978
    # Gross PnL = 9.978
    # Entry fee = 1.0 * 100.0 * 5.5/10000 = 0.055
    # Exit fee = 1.0 * 109.978 * 5.5/10000 = 0.0604879
    # Net PnL = 9.978 - 0.055 - 0.0604879 = 9.8625121
    # Realized R = Net / 10.0 = 0.98625121

    assert obs.net_pnl == Decimal("9.978") - Decimal("0.055") - Decimal("109.978") * (Decimal("5.5") / Decimal("10000"))
    assert obs.realized_r == obs.net_pnl / Decimal("10.0")


def test_fill_idempotent_identity(base_paper_policy, sample_intent_long, fresh_quote):
    simulator = PaperSimulator()

    obs1 = simulator.evaluate_entry(
        intent=sample_intent_long,
        quote=fresh_quote,
        paper_policy=base_paper_policy,
        portfolio_policy=PortfolioPolicy(policy_version="1.0", allocated_capital=Decimal("100"), minimum_unallocated_buffer=Decimal("0"), max_total_heat_ratio=Decimal("100.0")),
        current_portfolio_heat=Decimal("0"),
        allocation_reserved_risk=Decimal("0"),
        max_allowed_risk=Decimal("5.0"),
    )
    obs2 = simulator.evaluate_entry(
        intent=sample_intent_long,
        quote=fresh_quote,
        paper_policy=base_paper_policy,
        portfolio_policy=PortfolioPolicy(policy_version="1.0", allocated_capital=Decimal("100"), minimum_unallocated_buffer=Decimal("0"), max_total_heat_ratio=Decimal("100.0")),
        current_portfolio_heat=Decimal("0"),
        allocation_reserved_risk=Decimal("0"),
        max_allowed_risk=Decimal("5.0"),
    )

    assert obs1.fill_id == obs2.fill_id
