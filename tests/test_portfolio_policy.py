import pytest
from decimal import Decimal
from marketpilot.strategy.portfolio_policy import PortfolioPolicy

def test_effective_risk_capital_boundaries():
    # 3. usable 30 -> effective 27 (allocated 50)
    policy = PortfolioPolicy(policy_version="1", allocated_capital=Decimal("50.0"), minimum_unallocated_buffer=Decimal("3.0"))
    assert policy.calculate_effective_risk_capital(Decimal("30.0")) == Decimal("27.0")

    # 4. usable 28 -> effective 25 (allocated 25)
    policy = PortfolioPolicy(policy_version="1", allocated_capital=Decimal("25.0"), minimum_unallocated_buffer=Decimal("3.0"))
    assert policy.calculate_effective_risk_capital(Decimal("28.0")) == Decimal("25.0")

    # 5. usable 20 -> effective 17 (allocated 25)
    assert policy.calculate_effective_risk_capital(Decimal("20.0")) == Decimal("17.0")

    # 6. usable == buffer -> effective 0
    assert policy.calculate_effective_risk_capital(Decimal("3.0")) == Decimal("0.0")

    # 7. usable < buffer -> effective 0
    assert policy.calculate_effective_risk_capital(Decimal("2.0")) == Decimal("0.0")

    # Unallocated (Phase 5 disabled)
    policy = PortfolioPolicy(policy_version="1", allocated_capital=None)
    assert policy.calculate_effective_risk_capital(Decimal("100.0")) == Decimal("0.0")
