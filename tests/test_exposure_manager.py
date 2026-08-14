import pytest
from decimal import Decimal
import threading

from marketpilot.engines.exposure_manager import ExposureManager

def test_snapshot_immutability():
    em = ExposureManager()
    snap1 = em.snapshot()
    
    # Try to modify snapshot (should raise exception because it's frozen)
    with pytest.raises(Exception):
        snap1.total_heat = Decimal("100")

def test_atomic_reservation_success():
    em = ExposureManager()
    snap = em.snapshot()
    
    # Reserve
    success = em.reserve_if_version_matches("alloc-1", snap.exposure_version, Decimal("10"))
    assert success is True
    
    snap2 = em.snapshot()
    assert snap2.exposure_version != snap.exposure_version
    assert "alloc-1" in snap2.reserved_allocation_ids
    assert snap2.total_heat == Decimal("10")

def test_cas_stale_version_rejection():
    em = ExposureManager()
    snap1 = em.snapshot()
    
    # First reservation succeeds
    assert em.reserve_if_version_matches("alloc-1", snap1.exposure_version, Decimal("10")) is True
    
    # Second reservation with stale version fails
    assert em.reserve_if_version_matches("alloc-2", snap1.exposure_version, Decimal("20")) is False
    
    snap2 = em.snapshot()
    assert "alloc-2" not in snap2.reserved_allocation_ids
    assert snap2.total_heat == Decimal("10")

def test_zero_risk_reservation_rejection():
    em = ExposureManager()
    snap = em.snapshot()
    
    # Reject 0 risk
    assert em.reserve_if_version_matches("alloc-1", snap.exposure_version, Decimal("0")) is False
    
    # Reject negative risk
    assert em.reserve_if_version_matches("alloc-2", snap.exposure_version, Decimal("-5")) is False
    
    snap2 = em.snapshot()
    assert len(snap2.reserved_allocation_ids) == 0

def test_replace_all():
    em = ExposureManager()
    em.replace_all(["pos-1", "pos-2"], Decimal("50"))
    
    snap = em.snapshot()
    assert "pos-1" in snap.active_position_ids
    assert "pos-2" in snap.active_position_ids
    assert len(snap.reserved_allocation_ids) == 0
    assert snap.total_heat == Decimal("50")

def test_apply_confirmed_transition():
    em = ExposureManager()
    snap1 = em.snapshot()
    
    em.reserve_if_version_matches("alloc-1", snap1.exposure_version, Decimal("10"))
    
    # Transition
    em.apply_confirmed_transition("alloc-1", "pos-1", Decimal("10"))
    
    snap2 = em.snapshot()
    assert "alloc-1" not in snap2.reserved_allocation_ids
    assert "pos-1" in snap2.active_position_ids
    assert snap2.total_heat == Decimal("10")

def test_release_prepared_reservation():
    em = ExposureManager()
    snap1 = em.snapshot()
    
    em.reserve_if_version_matches("alloc-1", snap1.exposure_version, Decimal("10"))
    
    # Release
    em.release_prepared_reservation("alloc-1", Decimal("10"))
    
    snap2 = em.snapshot()
    assert "alloc-1" not in snap2.reserved_allocation_ids
    assert snap2.total_heat == Decimal("0")

def test_concurrent_state_access():
    em = ExposureManager()
    
    def worker(worker_id: int):
        for _ in range(50):
            snap = em.snapshot()
            em.reserve_if_version_matches(f"alloc-{worker_id}-{_}", snap.exposure_version, Decimal("1"))
            
    threads = []
    for i in range(10):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    snap = em.snapshot()
    # At least some reservations should have succeeded, and heat should match
    assert snap.total_heat == Decimal(str(len(snap.reserved_allocation_ids)))
