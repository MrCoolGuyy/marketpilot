import pytest
from marketpilot.models.registry import RegistrySnapshot, StrategyRegistryEntry, PromotionStatus
from marketpilot.models.causal import StrategyIdentity
from marketpilot.strategy.registry_service import StrategyRegistryService

def test_registry_service_exact_match():
    entry = StrategyRegistryEntry(
        strategy_id="StratA",
        strategy_version="v1",
        parameter_set_id="params-1",
        promotion_status=PromotionStatus.LIVE_ELIGIBLE,
        evidence_references=("ev-1",)
    )
    
    snapshot = RegistrySnapshot(
        registry_version="reg-100",
        entries=(entry,)
    )
    
    svc = StrategyRegistryService(snapshot)
    
    # 1. Exact match
    identity = StrategyIdentity(
        registry_version="reg-100",
        strategy_id="StratA",
        strategy_version="v1",
        parameter_set_id="params-1"
    )
    result = svc.resolve_exact(identity)
    assert isinstance(result, StrategyRegistryEntry)
    assert result.strategy_id == "StratA"
    
    # 2. Registry version mismatch
    identity_bad_reg = StrategyIdentity(
        registry_version="reg-99",
        strategy_id="StratA",
        strategy_version="v1",
        parameter_set_id="params-1"
    )
    result_bad_reg = svc.resolve_exact(identity_bad_reg)
    assert isinstance(result_bad_reg, str)
    assert "Registry version mismatch" in result_bad_reg
    
    # 3. Parameter set mismatch
    identity_bad_param = StrategyIdentity(
        registry_version="reg-100",
        strategy_id="StratA",
        strategy_version="v1",
        parameter_set_id="params-2"
    )
    result_bad_param = svc.resolve_exact(identity_bad_param)
    assert isinstance(result_bad_param, str)
    assert "not found" in result_bad_param

def test_registry_service_promotion_status():
    entry_research = StrategyRegistryEntry(
        strategy_id="StratB",
        strategy_version="v1",
        parameter_set_id="params-1",
        promotion_status=PromotionStatus.RESEARCH_ONLY,
        evidence_references=()
    )
    
    snapshot = RegistrySnapshot(
        registry_version="reg-100",
        entries=(entry_research,)
    )
    
    svc = StrategyRegistryService(snapshot)
    identity = StrategyIdentity(
        registry_version="reg-100",
        strategy_id="StratB",
        strategy_version="v1",
        parameter_set_id="params-1"
    )
    
    result = svc.resolve_exact(identity)
    assert isinstance(result, str)
    assert "not LIVE_ELIGIBLE" in result

