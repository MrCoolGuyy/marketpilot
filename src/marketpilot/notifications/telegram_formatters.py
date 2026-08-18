"""
MarketPilot Dashboard - Telegram Formatters.

Translates domain events and state into clean, HTML-safe Telegram presentation blocks.
Strictly outbound-only observability.
"""

from decimal import Decimal
from typing import Any, Optional
import html

# Domain Models
from marketpilot.models.causal import FinalCandidate
from marketpilot.models.portfolio import (
    PortfolioAdmissionDecision,
    PortfolioExposureSnapshot,
    EquitySnapshot,
    PortfolioAllocationToken
)

def escape_html(text: str | Any) -> str:
    """Escapes HTML characters for Telegram parse_mode='HTML'."""
    return html.escape(str(text))

def _na(val: Any) -> str:
    return str(val) if val is not None else "N/A"

def format_system_status(
    status: str,
    mode: str,
    env: str,
    version: str,
    daemon_state: str = "N/A",
    recovery_safe: str = "N/A",
    phase: str = "N/A",
    policy_version: str = "N/A",
    allocated_capital: str = "N/A",
    effective_capital: str = "N/A",
    current_heat: str = "N/A",
    active_lineages: int = 0,
    reserved_lineages: int = 0,
    last_cycle_id: str = "N/A",
    last_cycle_outcome: str = "N/A",
    telegram_state: str = "OK"
) -> str:
    return (
        f"🟢 <b>System Status</b>\n"
        f"State: <code>{escape_html(status)}</code>\n"
        f"Mode: <code>{escape_html(mode)}</code>\n"
        f"Environment: <code>{escape_html(env)}</code>\n"
        f"Version: <code>{escape_html(version)}</code>\n\n"
        f"Daemon State: <code>{escape_html(daemon_state)}</code>\n"
        f"Recovery SAFE: <code>{escape_html(recovery_safe)}</code>\n"
        f"Phase: <code>{escape_html(phase)}</code>\n"
        f"Policy Version: <code>{escape_html(policy_version)}</code>\n\n"
        f"Allocated Capital: <code>{escape_html(allocated_capital)}</code>\n"
        f"Effective Capital: <code>{escape_html(effective_capital)}</code>\n"
        f"Current Heat: <code>{escape_html(current_heat)}</code>\n"
        f"Active Lineages: {active_lineages}\n"
        f"Reserved Lineages: {reserved_lineages}\n\n"
        f"Last Cycle ID: <code>{escape_html(last_cycle_id)}</code>\n"
        f"Last Cycle Outcome: <code>{escape_html(last_cycle_outcome)}</code>\n"
        f"Telegram State: <code>{escape_html(telegram_state)}</code>\n\n"
        f"Network Permit: NOT AVAILABLE IN PHASE 5\n"
        f"Orders Submitted: 0"
    )


def format_phase4_cycle(
    cycle_id: str,
    time_str: str,
    mode: str,
    env: str,
    outcome: str,
    universe_size: int,
    market_qualified: int,
    signals: int,
    priced: int,
    evidence_evaluated: int,
    eligible: int,
    admitted: int,
    rejected: int,
    rejections_evidence: int,
    rejections_economics: int,
    rejections_heat: int,
    rejections_lineage: int,
    current_heat: str = "N/A",
    heat_limit: str = "N/A",
    effective_capital: str = "N/A",
    active_lineages: int = 0,
    reservations: int = 0,
    top_candidate: Optional[FinalCandidate] = None,
    top_decision: Optional[PortfolioAdmissionDecision] = None
) -> str:
    icon = "✅" if admitted > 0 else "ℹ️"
    if outcome.startswith("FAIL") or outcome.startswith("ERROR"):
        icon = "❌"

    msg = (
        f"{icon} <b>Cycle Summary</b>\n"
        f"Cycle ID: <code>{escape_html(cycle_id)}</code>\n"
        f"Time: {escape_html(time_str)}\n"
        f"Mode: <code>{escape_html(mode)}</code>\n"
        f"Exchange: <code>{escape_html(env)}</code>\n"
        f"Outcome: <code>{escape_html(outcome)}</code>\n\n"

        f"Universe Size: {universe_size}\n"
        f"Market Qualified: {market_qualified}\n"
        f"Signals: {signals}\n"
        f"Priced: {priced}\n"
        f"Evidence Evaluated: {evidence_evaluated}\n"
        f"Eligible Candidates: {eligible}\n"
        f"Portfolio Admitted: {admitted}\n"
        f"Rejected: {rejected}\n\n"

        f"<b>Rejections</b>\n"
        f"Evidence: {rejections_evidence}\n"
        f"Economics: {rejections_economics}\n"
        f"Portfolio Heat: {rejections_heat}\n"
        f"Active Lineage: {rejections_lineage}\n\n"
    )

    if top_candidate:
        dec_str = "ADMITTED" if (top_decision and top_decision.is_admitted) else "REJECTED"
        sym = top_candidate.priced_candidate.intent.symbol
        side = top_candidate.priced_candidate.intent.direction.value
        strat = f"{top_candidate.priced_candidate.intent.identity.strategy_id} v{top_candidate.priced_candidate.intent.identity.strategy_version}"
        ev = top_candidate.size_aware_economics.final_net_ev_r
        risk = top_candidate.sizing.provisional_quantity * abs(top_candidate.priced_candidate.executable_entry_price - top_candidate.sizing.effective_stop_price)

        msg += (
            f"<b>Top Candidate</b>\n"
            f"Symbol: {escape_html(sym)}\n"
            f"Side: {escape_html(side)}\n"
            f"Strategy: {escape_html(strat)}\n"
            f"FinalNetEV: {ev:.4f}\n"
            f"Risk: {risk:.2f}\n"
            f"Decision: {dec_str}\n\n"
        )

    msg += (
        f"<b>Portfolio State</b>\n"
        f"Current Heat: {escape_html(current_heat)}\n"
        f"Heat Limit: {escape_html(heat_limit)}\n"
        f"Effective Risk Capital: {escape_html(effective_capital)}\n"
        f"Active Lineages: {active_lineages}\n"
        f"Reservations: {reservations}\n\n"

        f"Orders Submitted: 0"
    )

    return msg


def format_phase5_admission(
    candidate: FinalCandidate,
    decision: PortfolioAdmissionDecision,
    exposure: PortfolioExposureSnapshot,
    equity: EquitySnapshot
) -> str:
    sym = candidate.priced_candidate.intent.symbol
    side = candidate.priced_candidate.intent.direction.value
    strat_id = candidate.priced_candidate.intent.identity.strategy_id
    strat_ver = candidate.priced_candidate.intent.identity.strategy_version

    entry = candidate.priced_candidate.executable_entry_price
    stop = candidate.sizing.effective_stop_price
    qty = candidate.sizing.provisional_quantity
    risk_unit = abs(entry - stop)
    risk_amt = qty * risk_unit

    # Evidence
    evidence = candidate.assessment.status.value
    expected_gross = candidate.pre_size_economics.approved_expected_gross_r
    expected_costs = candidate.pre_size_economics.pre_size_expected_cost_r
    final_ev = candidate.size_aware_economics.final_net_ev_r

    # Portfolio
    alloc_cap = equity.configured_allocated_capital
    usable_cap = equity.usable_account_value
    eff_cap = min(alloc_cap, usable_cap)

    heat_before = exposure.total_risk_amount
    heat_after = exposure.total_risk_amount + risk_amt
    heat_limit = exposure.policy_limit_risk_amount
    rem_budget = heat_limit - heat_after

    act_lin = len(exposure.active_position_ids)
    res_lin = len(exposure.reserved_allocation_ids)
    max_lin = exposure.policy_max_lineages

    # Token
    tok = decision.token
    alloc_id = tok.reservation_identity if tok else "N/A"
    lin_id = tok.lineage_identity if tok else "N/A"

    return (
        f"🟡 <b>MARKETPILOT — TRADE CANDIDATE</b>\n"
        f"PAPER | BYBIT MAINNET READ-ONLY\n\n"
        f"<b>{escape_html(sym)} — {escape_html(side)}</b>\n"
        f"{escape_html(strat_id)} v{escape_html(strat_ver)}\n\n"

        f"📌 <b>TRADE PLAN</b>\n"
        f"Entry             : <code>{entry}</code>\n"
        f"Effective Stop    : <code>{stop}</code>\n"
        f"Take Profit       : N/A\n"
        f"Quantity          : <code>{qty}</code>\n"
        f"Risk / Unit       : <code>{risk_unit:.4f}</code>\n"
        f"Candidate Risk    : <code>{risk_amt:.2f}</code> USDT\n"
        f"Estimated RR      : N/A\n\n"

        f"📊 <b>STRATEGY EVIDENCE</b>\n"
        f"Evidence          : {escape_html(evidence)}\n"
        f"Validation Trades : N/A\n"
        f"Historical WinRate: N/A\n"
        f"Avg Realized R    : N/A\n"
        f"Expected Gross R  : {expected_gross:.4f}\n"
        f"Expected Costs    : {expected_costs:.4f}\n"
        f"Final Net EV      : {final_ev:.4f}\n\n"

        f"🧠 <b>SIGNAL</b>\n"
        f"Regime            : N/A\n"
        f"Trend Age         : N/A\n"
        f"Strategy Score    : N/A\n"
        f"Confidence        : N/A\n\n"

        f"💼 <b>PORTFOLIO</b>\n"
        f"Allocated Capital : <code>{alloc_cap:.2f}</code>\n"
        f"Usable Account    : <code>{usable_cap:.2f}</code>\n"
        f"Effective Capital : <code>{eff_cap:.2f}</code>\n"
        f"Risk Before       : <code>{heat_before:.2f}</code>\n"
        f"Risk After        : <code>{heat_after:.2f}</code>\n"
        f"Heat Before       : <code>{(heat_before/eff_cap)*100 if eff_cap > 0 else 0:.1f}%</code>\n"
        f"Heat After        : <code>{(heat_after/eff_cap)*100 if eff_cap > 0 else 0:.1f}%</code>\n"
        f"Heat Limit        : <code>{heat_limit:.2f}</code>\n"
        f"Remaining Budget  : <code>{rem_budget:.2f}</code>\n"
        f"Active Lineages   : {act_lin}\n"
        f"Reservations      : {res_lin}\n"
        f"Max Lineages      : {max_lin}\n\n"

        f"✅ <b>ADMITTED</b>\n\n"

        f"🔐 <b>CAPITAL ADMISSION</b>\n"
        f"Allocation        : <code>{alloc_id}</code>\n"
        f"Lineage           : <code>{lin_id}</code>\n"
        f"Exposure Version  : <code>{exposure.exposure_version}</code>\n"
        f"Policy            : <code>{tok.portfolio_policy_version if tok else 'N/A'}</code>\n"
        f"Journal           : DURABLE\n\n"

        f"⚠️ <b>EXECUTION BOUNDARY</b>\n"
        f"Network Permit    : NOT ISSUED\n"
        f"Exchange Order    : NOT SUBMITTED\n"
        f"Actual PnL        : N/A — no execution yet"
    )

def format_portfolio_rejection(
    candidate: FinalCandidate,
    decision: PortfolioAdmissionDecision,
    exposure: PortfolioExposureSnapshot
) -> str:
    sym = candidate.priced_candidate.intent.symbol
    side = candidate.priced_candidate.intent.direction.value
    strat = f"{candidate.priced_candidate.intent.identity.strategy_id} v{candidate.priced_candidate.intent.identity.strategy_version}"
    entry = candidate.priced_candidate.executable_entry_price
    stop = candidate.sizing.effective_stop_price
    qty = candidate.sizing.provisional_quantity
    risk_amt = qty * abs(entry - stop)
    ev = candidate.size_aware_economics.final_net_ev_r
    ev_status = candidate.assessment.status.value

    heat_before = exposure.total_risk_amount
    heat_limit = exposure.policy_limit_risk_amount
    rem_budget = heat_limit - heat_before

    rej = decision.rejection
    code = rej.rejection_code if rej else "UNKNOWN"
    reason = rej.reason if rej else "Unknown"

    msg = (
        f"⛔ <b>Portfolio Rejection</b>\n\n"
        f"Symbol: <b>{escape_html(sym)}</b>\n"
        f"Side: {escape_html(side)}\n"
        f"Strategy: {escape_html(strat)}\n"
        f"Entry: <code>{entry}</code>\n"
        f"Stop: <code>{stop}</code>\n"
        f"Quantity: <code>{qty}</code>\n"
        f"Candidate Risk: <code>{risk_amt:.2f}</code>\n"
        f"FinalNetEV: {ev:.4f}\n"
        f"Evidence Status: {escape_html(ev_status)}\n\n"

        f"<b>Portfolio</b>\n"
        f"Heat Before: <code>{heat_before:.2f}</code>\n"
        f"Projected Heat: <code>{heat_before + risk_amt:.2f}</code>\n"
        f"Heat Limit: <code>{heat_limit:.2f}</code>\n"
        f"Required Risk: <code>{risk_amt:.2f}</code>\n"
        f"Remaining Budget: <code>{rem_budget:.2f}</code>\n\n"

        f"<b>Decision</b>\n"
        f"Code: <code>{escape_html(code)}</code>\n"
        f"Reason: {escape_html(reason)}\n"
    )

    return msg

def format_evidence_rejection(
    symbol: str,
    side: str,
    strategy: str,
    entry: Optional[Decimal],
    evidence_status: str,
    reason: str
) -> str:
    msg = (
        f"⛔ <b>Evidence Rejection</b>\n\n"
        f"Symbol: <b>{escape_html(symbol)}</b>\n"
        f"Side: {escape_html(side)}\n"
        f"Strategy: {escape_html(strategy)}\n"
        f"Entry: <code>{entry if entry else 'N/A'}</code>\n"
        f"Evidence Status: {escape_html(evidence_status)}\n\n"
        f"Sample Count: N/A\n"
        f"Min Required: N/A\n"
        f"Historical Metrics: N/A\n\n"
        f"Reason: {escape_html(reason)}\n"
        f"Stage: EVIDENCE\n"
    )
    return msg

def format_reservation_committed(
    token: PortfolioAllocationToken
) -> str:
    sym = token.symbol
    side = token.direction
    risk = token.candidate_risk_amount
    qty = token.quantity
    entry = token.executable_entry
    stop = token.effective_stop
    lin_id = token.lineage_identity
    alloc_id = token.reservation_identity

    return (
        f"🔐 <b>RESERVATION COMMITTED</b>\n\n"
        f"Symbol: <b>{escape_html(sym)}</b> {escape_html(side)}\n"
        f"Risk: <code>{risk:.2f}</code>\n"
        f"Quantity: <code>{qty}</code>\n"
        f"Entry: <code>{entry}</code>\n"
        f"Effective Stop: <code>{stop}</code>\n\n"

        f"Lineage: <code>{lin_id}</code>\n"
        f"Allocation Token: <code>{alloc_id}</code>\n"
        f"Policy Version: <code>{token.portfolio_policy_version}</code>\n"
        f"Exposure Version: <code>{token.portfolio_snapshot_version}</code>\n"
        f"Journal State: COMMITTED\n\n"

        f"⚠️ <b>EXECUTION BOUNDARY</b>\n"
        f"Network Permit: NOT ISSUED\n"
        f"Exchange Order: NOT SUBMITTED"
    )

def format_safety_alert(component: str, message: str) -> str:
    return (
        f"⚠️ <b>SAFETY ALERT</b>\n"
        f"Component: <code>{escape_html(component)}</code>\n"
        f"Details:\n<pre>{escape_html(message)}</pre>\n\n"
        f"Network Permit: NOT ISSUED\n"
        f"Exchange Order: NOT SUBMITTED"
    )
