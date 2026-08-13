"""Tests for Execution Engine under chaos conditions."""

import time
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest

from marketpilot.engines.execution_engine import ExecutionEngine
from marketpilot.engines.circuit_breaker import CircuitBreaker, SystemState
from marketpilot.models.trade import TradePlan
from marketpilot.models.strategy import SignalDirection
from marketpilot.models.execution import ExecutionStatus
from marketpilot.core.exceptions import ExchangeAPIError, ExchangeConnectionError
from marketpilot.models.regime import MarketRegime

@pytest.mark.asyncio
async def test_execution_engine_rate_limit_backoff():
    client_mock = MagicMock()
    circuit_breaker = CircuitBreaker()
    engine = ExecutionEngine(client=client_mock, circuit_breaker=circuit_breaker)
    engine.max_retries = 2
    
    # Mock place_order to raise Rate Limit twice, then succeed
    call_count = 0
    async def mock_place_order(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise ExchangeAPIError(status_code=10002, message="Rate Limit", ret_code=10002)
        return {"result": {"orderId": "12345"}}
        
    client_mock.place_order = AsyncMock(side_effect=mock_place_order)
    client_mock.get_order_status = AsyncMock(return_value={}) # Idempotency check finds nothing
    client_mock.set_trading_stop = AsyncMock(return_value={})
    
    plan = TradePlan(
        decision_id="test-1",
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        entry=Decimal("100"),
        sl=Decimal("90"),
        tp=Decimal("120"),
        qty=Decimal("1.0"),
        risk=Decimal("10"),
        strategy="Test",
        confidence=Decimal("100"),
        market_regime=MarketRegime.TRENDING_BULL,
        market_quality=Decimal("100"),
        reason="Test",
        timestamp=time.time(),
        expected_rr=Decimal("2.0")
    )
    
    result = await engine.execute(plan)
    
    # It should have backed off twice, then succeeded
    assert result.status == ExecutionStatus.SUCCESS
    assert result.retry_count == 2
    assert result.exchange_order_id == "12345"
    assert circuit_breaker.state == SystemState.NORMAL
    
@pytest.mark.asyncio
async def test_execution_engine_circuit_breaker_halt():
    client_mock = MagicMock()
    circuit_breaker = CircuitBreaker()
    circuit_breaker.max_consecutive_failures = 3
    engine = ExecutionEngine(client=client_mock, circuit_breaker=circuit_breaker)
    engine.max_retries = 3
    
    # Mock place_order to raise a general Exchange error
    client_mock.place_order = AsyncMock(side_effect=ExchangeAPIError(status_code=500, message="Internal Error", ret_code=10000))
    client_mock.get_order_status = AsyncMock(return_value={}) 
    
    plan = TradePlan(
        decision_id="test-2",
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        entry=Decimal("100"),
        sl=Decimal("90"),
        tp=Decimal("120"),
        qty=Decimal("1.0"),
        risk=Decimal("10"),
        strategy="Test",
        confidence=Decimal("100"),
        market_regime=MarketRegime.TRENDING_BULL,
        market_quality=Decimal("100"),
        reason="Test",
        timestamp=time.time(),
        expected_rr=Decimal("2.0")
    )
    
    with pytest.raises(RuntimeError, match="SYSTEM HALTED"):
        await engine.execute(plan)
        
    assert circuit_breaker.state == SystemState.HALTED

@pytest.mark.asyncio
async def test_execution_engine_idempotency_guard():
    client_mock = MagicMock()
    circuit_breaker = CircuitBreaker()
    engine = ExecutionEngine(client=client_mock, circuit_breaker=circuit_breaker)
    engine.max_retries = 2
    
    # Attempt 1: Timeout (Execution throws Exception)
    async def mock_place_order_timeout(*args, **kwargs):
        raise ExchangeConnectionError("Network Timeout")
        
    client_mock.place_order = AsyncMock(side_effect=mock_place_order_timeout)
    
    # Attempt 2: get_order_status reveals the order ACTUALLY went through
    client_mock.get_order_status = AsyncMock(return_value={
        "result": {
            "list": [
                {
                    "orderId": "idemp-456",
                    "cumExecQty": "1.0",
                    "avgPrice": "100.0"
                }
            ]
        }
    })
    
    plan = TradePlan(
        decision_id="test-idemp",
        symbol="BTCUSDT",
        direction=SignalDirection.LONG,
        entry=Decimal("100"),
        sl=Decimal("90"),
        tp=Decimal("120"),
        qty=Decimal("1.0"),
        risk=Decimal("10"),
        strategy="Test",
        confidence=Decimal("100"),
        market_regime=MarketRegime.TRENDING_BULL,
        market_quality=Decimal("100"),
        reason="Test",
        timestamp=time.time(),
        expected_rr=Decimal("2.0")
    )
    
    result = await engine.execute(plan)
    
    # The result should be SUCCESS without calling place_order again!
    assert result.status == ExecutionStatus.SUCCESS
    assert result.exchange_order_id == "idemp-456"
    assert result.executed_qty == Decimal("1.0")
    assert result.executed_price == Decimal("100.0")
    assert result.retry_count == 1 # Found on 1st retry
