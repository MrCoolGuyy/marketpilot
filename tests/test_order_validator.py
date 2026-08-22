"""Tests for Order Validator (Phase 6A)."""

import pytest
from decimal import Decimal

from marketpilot.engines.order_validator import OrderValidator, OrderValidationRejection
from marketpilot.models.execution import ExecutionIntent, ValidatedOrderSpec
from marketpilot.models.execution_policy import ExecutionValidationPolicy
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.core.enums import AssetType


@pytest.fixture
def base_intent() -> ExecutionIntent:
    return ExecutionIntent(
        intent_id="INT-1",
        allocation_token_id="ALLOC-1",
        logical_order_id="LOG-1",
        symbol="BTCUSDT",
        side="LONG",
        original_qty=Decimal("1.2345"),
        executable_entry=Decimal("100.1234"),
        effective_stop=Decimal("90.9876"),
        take_profit=Decimal("120.1111"),
        environment="PAPER",
    )


@pytest.fixture
def instrument() -> InstrumentInfo:
    return InstrumentInfo(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        status="Trading",
        tick_size="0.01",
        min_order_qty="0.001",
        max_order_qty="100",
        qty_step="0.001",
        min_leverage="1",
        max_leverage="100",
    )


def test_order_validator_quantization_long(
    base_intent: ExecutionIntent, instrument: InstrumentInfo
) -> None:
    policy = ExecutionValidationPolicy(
        max_quantity_deviation_bps=500, allow_quantity_increase=False
    )
    validator = OrderValidator(policy)

    spec = validator.validate_intent(base_intent, instrument)

    # Qty 1.2345, step 0.001 -> 1.234 (floored)
    assert spec.quantized_qty == Decimal("1.234")
    # LONG entry 100.1234, tick 0.01 -> floor -> 100.12
    assert spec.quantized_price == Decimal("100.12")
    # LONG stop 90.9876, tick 0.01 -> ceil (towards entry) -> 90.99
    assert spec.quantized_stop == Decimal("90.99")
    # LONG tp 120.1111, tick 0.01 -> floor -> 120.11
    assert spec.quantized_tp == Decimal("120.11")
    assert spec.spec_hash is not None


def test_order_validator_quantization_short(
    base_intent: ExecutionIntent, instrument: InstrumentInfo
) -> None:
    intent = ExecutionIntent(
        **base_intent.model_dump(exclude={"side", "effective_stop", "take_profit"}),
        side="SHORT",
        effective_stop=Decimal("110.9876"),
        take_profit=Decimal("80.1111"),
    )
    policy = ExecutionValidationPolicy(
        max_quantity_deviation_bps=500, allow_quantity_increase=False
    )
    validator = OrderValidator(policy)

    spec = validator.validate_intent(intent, instrument)




def test_order_validator_missing_tests():
    from decimal import Decimal
    from marketpilot.engines.order_validator import OrderValidator, OrderValidationRejection
    from marketpilot.models.execution import ExecutionIntent
    from marketpilot.models.execution_policy import ExecutionValidationPolicy
    from marketpilot.models.instrument import InstrumentInfo
    from marketpilot.core.enums import AssetType
    import pytest

    validator = OrderValidator(
        policy=ExecutionValidationPolicy(require_canonical_tp=True, max_quantity_deviation_bps=2000)
    )

    intent = ExecutionIntent(
        intent_id="INT-MISSING-TESTS",
        allocation_token_id="ALLOC-123",
        logical_order_id="LOG-123",
        symbol="BTCUSDT",
        side="LONG",
        original_qty=Decimal("1.0"),
        executable_entry=Decimal("100.0"),
        effective_stop=Decimal("90.0"),
        take_profit=Decimal("120.0"),
        environment="PAPER",
        version="1.0",
        instrument_type="LINEAR"
    )
    
    instrument = InstrumentInfo(
        symbol="BTCUSDT",
        asset_type=AssetType.LINEAR,
        base_coin="BTC",
        quote_coin="USDT",
        status="Trading",
        tick_size="0.1",
        qty_step="0.1",
        min_order_qty="0.1",
        max_order_qty="100.0",
        min_notional_value="1.0"
    )

    # 4. Missing explicit quantity-floor/no-upsize test
    instrument_floor = instrument.model_copy(update={"qty_step": "2.0", "min_order_qty": "2.0"})
    with pytest.raises(OrderValidationRejection) as exc:
        validator.validate_intent(intent, instrument_floor)
    assert "below min" in str(exc.value).lower()

    # 3. Missing minimum-order/excess-risk rejection test
    instrument_notional = instrument.model_copy(update={"qty_step": "0.1", "min_order_qty": "1.5"})
    with pytest.raises(OrderValidationRejection) as exc:
        validator.validate_intent(intent, instrument_notional)
    assert "below min" in str(exc.value).lower()

    # 5. Missing explicit stop-widening prohibition tests
    instrument_stop = instrument.model_copy(update={"tick_size": "1.0"})
    intent_stop = intent.model_copy(update={"effective_stop": Decimal("90.1")})
    spec = validator.validate_intent(intent_stop, instrument_stop)
    assert spec.quantized_stop == Decimal("91.0")

    intent_short = intent.model_copy(update={"side": "SHORT", "effective_stop": Decimal("109.9"), "take_profit": Decimal("80.0")})
    spec = validator.validate_intent(intent_short, instrument_stop)
    assert spec.quantized_stop == Decimal("109.0")

def test_operator_policy_immutability():
    from marketpilot.strategy.portfolio_policy import PortfolioPolicy
    from decimal import Decimal
    import pytest
    from pydantic import ValidationError

    policy = PortfolioPolicy(policy_version="1", allocated_capital=Decimal("100"), max_simultaneous_lineages=1)
    
    with pytest.raises(ValidationError):
        policy.max_simultaneous_lineages = 2
