import pytest
from marketpilot.engines.reconciler_engine import ReconcilerEngine
from marketpilot.models.recovery import ExchangeRecoverySnapshot
import time

def test_startup_reconciliation_exact_match():
    engine = ReconcilerEngine()
    snapshot = ExchangeRecoverySnapshot(
        snapshot_id="snap1",
        timestamp=time.time(),
        open_orders=("order-1", "order-2"),
        active_positions=("pos-1",)
    )
    
    result = engine.reconcile_startup(
        journal_open_orders={"order-1", "order-2"},
        journal_active_positions={"pos-1"},
        snapshot=snapshot,
        order_history={}
    )
    
    assert result.success is True
    assert len(result.reconciled_records) == 3
    assert all(r.issue_type == "MATCHED" for r in result.reconciled_records)

def test_startup_reconciliation_orphan():
    engine = ReconcilerEngine()
    snapshot = ExchangeRecoverySnapshot(
        snapshot_id="snap1",
        timestamp=time.time(),
        open_orders=("order-1",), # Exchange has order-1, journal empty
        active_positions=()
    )
    
    result = engine.reconcile_startup(
        journal_open_orders=set(),
        journal_active_positions=set(),
        snapshot=snapshot,
        order_history={}
    )
    
    assert result.success is False
    assert len(result.reconciled_records) == 1
    assert result.reconciled_records[0].issue_type == "EXCHANGE_ORPHAN"

def test_startup_reconciliation_ghost_terminal():
    engine = ReconcilerEngine()
    snapshot = ExchangeRecoverySnapshot(
        snapshot_id="snap1",
        timestamp=time.time(),
        open_orders=(), # Exchange has no orders
        active_positions=()
    )
    
    # But order history shows it was filled
    order_history = {
        "order-1": {"orderStatus": "Filled"}
    }
    
    result = engine.reconcile_startup(
        journal_open_orders={"order-1"}, # Journal thinks order is open
        journal_active_positions=set(),
        snapshot=snapshot,
        order_history=order_history
    )
    
    assert result.success is True
    assert len(result.reconciled_records) == 1
    assert result.reconciled_records[0].issue_type == "MATCHED"
    
def test_startup_reconciliation_ghost_unresolved():
    engine = ReconcilerEngine()
    snapshot = ExchangeRecoverySnapshot(
        snapshot_id="snap1",
        timestamp=time.time(),
        open_orders=(),
        active_positions=()
    )
    
    result = engine.reconcile_startup(
        journal_open_orders={"order-1"},
        journal_active_positions=set(),
        snapshot=snapshot,
        order_history={} # No history
    )
    
    assert result.success is False
    assert result.reconciled_records[0].issue_type == "JOURNAL_GHOST"
