"""
MarketPilot - Deterministic Paper Simulator Engine.
"""
from datetime import UTC, datetime
from decimal import Decimal

from marketpilot.models.execution import (
    ExecutionIntent,
    ExecutionQuoteSnapshot,
    PaperFillRole,
    PaperPositionState,
    PaperSimulationObservation,
)
from marketpilot.models.execution_policy import PaperExecutionPolicy
from marketpilot.models.market import Kline
from marketpilot.models.strategy import SignalDirection
from marketpilot.strategy.portfolio_policy import PortfolioPolicy


class PaperSimulationRejected(Exception):
    """Raised when a PAPER execution is deterministically rejected by the simulator."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(self.reason)


class PaperSimulator:
    """
    Pure domain engine for deterministic PAPER execution.
    Contains no journal or external dependencies.
    """

    @staticmethod
    def _get_current_time() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _generate_fill_id(
        logical_order_id: str,
        role: PaperFillRole,
        quote_or_candle_id: str,
        policy_version: str,
    ) -> str:
        # Deterministic string concatenation
        return f"PF-{logical_order_id}-{role.value}-{quote_or_candle_id}-{policy_version}"

    def evaluate_entry(
        self,
        intent: ExecutionIntent,
        quote: ExecutionQuoteSnapshot,
        paper_policy: PaperExecutionPolicy,
        portfolio_policy: PortfolioPolicy,
        current_portfolio_heat: Decimal,
        allocation_reserved_risk: Decimal,
        max_allowed_risk: Decimal,
    ) -> PaperSimulationObservation:
        """
        Evaluates a prospective ENTRY fill against a fresh quote.
        Raises PaperSimulationRejected on any policy/risk violation.
        """
        # 1. Quote Freshness
        now = self._get_current_time()
        age_ms = (now - quote.received_at).total_seconds() * 1000
        if age_ms > paper_policy.max_quote_age_ms:
            raise PaperSimulationRejected(f"Quote stale. Age: {age_ms}ms > {paper_policy.max_quote_age_ms}ms")

        if quote.bid <= 0 or quote.ask <= 0 or quote.ask < quote.bid:
            raise PaperSimulationRejected("Invalid quote bid/ask spread")
        if quote.symbol != intent.symbol:
            raise PaperSimulationRejected("Quote symbol mismatch")

        if intent.take_profit is None:
            raise PaperSimulationRejected("Canonical TP is required for PAPER v1")

        # 2. Entry Fill Model
        slippage_factor = paper_policy.entry_slippage_bps / Decimal("10000")
        if intent.side == SignalDirection.LONG:
            base_price = quote.ask
            simulated_fill = base_price * (Decimal("1") + slippage_factor)

            # 3. Entry Semantic Collapse
            if not (intent.effective_stop < simulated_fill < intent.take_profit):
                raise PaperSimulationRejected("Entry slippage collapsed LONG TP/SL relationship")
        else:
            base_price = quote.bid
            simulated_fill = base_price * (Decimal("1") - slippage_factor)

            if not (intent.take_profit < simulated_fill < intent.effective_stop):
                raise PaperSimulationRejected("Entry slippage collapsed SHORT TP/SL relationship")

        # 4. Pre-Open Risk
        actual_risk = intent.original_qty * abs(simulated_fill - intent.effective_stop)

        if actual_risk > max_allowed_risk:
            raise PaperSimulationRejected("Prospective actual risk exceeds hard policy ceiling")

        # Risk replacement: do not double count reservation
        prospective_total_risk = current_portfolio_heat - allocation_reserved_risk + actual_risk

        if prospective_total_risk > portfolio_policy.max_total_heat_ratio:
            raise PaperSimulationRejected("Prospective portfolio heat breach")


        # 5. Fee
        taker_fee_factor = paper_policy.taker_fee_bps / Decimal("10000")
        entry_fee = abs(intent.original_qty * simulated_fill) * taker_fee_factor

        # 6. ID
        fill_id = self._generate_fill_id(
            intent.logical_order_id,
            PaperFillRole.ENTRY,
            quote.quote_id,
            paper_policy.version,
        )

        return PaperSimulationObservation(
            fill_id=fill_id,
            role=PaperFillRole.ENTRY,
            qty=intent.original_qty,
            fill_price=simulated_fill,
            fee=entry_fee,
            timestamp=now.timestamp(),
            quote_id=quote.quote_id,
        )

    def evaluate_lifecycle(
        self,
        position: PaperPositionState,
        candle: Kline,
        paper_policy: PaperExecutionPolicy,
    ) -> PaperSimulationObservation | None:
        """
        Evaluates a post-entry closed candle for TP/SL triggers.
        Returns the terminal observation if triggered.
        """
        if not candle.is_closed:
            return None

        # Fully post-entry rule
        # The candle's interval must start AT OR AFTER the entry time.
        candle_open_timestamp = candle.open_time.timestamp()
        if candle_open_timestamp < position.entry_timestamp:
            return None

        triggered_sl = False
        triggered_tp = False

        if position.side == SignalDirection.LONG:
            if Decimal(candle.high) >= position.canonical_tp:
                triggered_tp = True
            if Decimal(candle.low) <= position.canonical_stop:
                triggered_sl = True
        else:
            if Decimal(candle.low) <= position.canonical_tp:
                triggered_tp = True
            if Decimal(candle.high) >= position.canonical_stop:
                triggered_sl = True

        if not triggered_sl and not triggered_tp:
            return None

        # Ambiguous policy
        if triggered_sl and triggered_tp:
            if paper_policy.ambiguous_candle_policy == "STOP_FIRST":
                triggered_tp = False
                triggered_sl = True

        # Gap and Slippage Semantics
        slippage_factor = paper_policy.exit_slippage_bps / Decimal("10000")

        if triggered_sl:
            role = PaperFillRole.SL_EXIT
            if position.side == SignalDirection.LONG:
                trigger_base = min(position.canonical_stop, Decimal(candle.open))
                exit_fill = trigger_base * (Decimal("1") - slippage_factor)
            else:
                trigger_base = max(position.canonical_stop, Decimal(candle.open))
                exit_fill = trigger_base * (Decimal("1") + slippage_factor)
        else:
            role = PaperFillRole.TP_EXIT
            if position.side == SignalDirection.LONG:
                trigger_base = position.canonical_tp
                exit_fill = trigger_base * (Decimal("1") - slippage_factor)
            else:
                trigger_base = position.canonical_tp
                exit_fill = trigger_base * (Decimal("1") + slippage_factor)

        # Fees
        taker_fee_factor = paper_policy.taker_fee_bps / Decimal("10000")
        exit_fee = abs(position.qty * exit_fill) * taker_fee_factor
        entry_fee = abs(position.qty * position.entry_fill) * taker_fee_factor

        # PnL
        if position.side == SignalDirection.LONG:
            gross_pnl = position.qty * (exit_fill - position.entry_fill)
        else:
            gross_pnl = position.qty * (position.entry_fill - exit_fill)

        net_pnl = gross_pnl - entry_fee - exit_fee

        # Realized R
        actual_initial_risk = position.qty * abs(position.entry_fill - position.canonical_stop)
        realized_r = net_pnl / actual_initial_risk if actual_initial_risk > 0 else Decimal("0")

        # Identity
        candle_id = f"{candle.open_time}"
        fill_id = self._generate_fill_id(
            position.position_id,
            role,
            candle_id,
            paper_policy.version,
        )

        return PaperSimulationObservation(
            fill_id=fill_id,
            role=role,
            qty=position.qty,
            fill_price=exit_fill,
            fee=exit_fee,
            timestamp=candle.open_time.timestamp(),
            candle_timestamp=candle.open_time.timestamp(),
            net_pnl=net_pnl,
            realized_r=realized_r,
        )
