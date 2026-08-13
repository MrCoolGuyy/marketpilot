"""
MarketPilot Engines - Execution Engine.

Responsible for safely submitting orders to the exchange.
Implements Idempotency Guard and smart retry policies based on error types.
"""

from __future__ import annotations

import time
import asyncio
from decimal import Decimal
from typing import Any

from loguru import logger

from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.trade import TradePlan
from marketpilot.models.execution import ExecutionStatus, ExecutionResult
from marketpilot.engines.circuit_breaker import CircuitBreaker, SystemState
from marketpilot.core.exceptions import ExchangeAPIError, ExchangeConnectionError

class ExecutionEngine:
    """Safely executes trade plans with retries, idempotency, and circuit breaking."""

    def __init__(self, client: BybitClient, circuit_breaker: CircuitBreaker):
        self._client = client
        self._circuit = circuit_breaker
        self.max_retries = 3

    async def _query_order_status(self, symbol: str, client_order_id: str) -> dict[str, Any] | None:
        """Queries the exchange to see if an order exists."""
        try:
            # Bybit 'get_open_orders' allows filtering by orderLinkId
            result = await self._client.get_order_status(symbol=symbol, order_link_id=client_order_id)
            if "result" in result and "list" in result["result"] and len(result["result"]["list"]) > 0:
                return result["result"]["list"][0]
        except Exception as e:
            logger.warning(f"Failed to query order status for {client_order_id}: {e}")
        return None

    async def execute(self, plan: TradePlan) -> ExecutionResult:
        """Attempt to execute a trade plan safely."""
        self._circuit.assert_healthy()
        
        start_ms = time.time() * 1000
        client_order_id = plan.decision_id
        
        attempt = 0
        while attempt <= self.max_retries:
            self._circuit.assert_healthy()
            
            # Idempotency Guard
            if attempt > 0:
                existing_order = await self._query_order_status(plan.symbol, client_order_id)
                if existing_order:
                    logger.info(f"Idempotency Guard triggered: Order {client_order_id} already exists.")
                    return self._build_result(
                        status=ExecutionStatus.SUCCESS,
                        plan=plan,
                        client_order_id=client_order_id,
                        exchange_order_id=existing_order.get("orderId"),
                        executed_qty=Decimal(existing_order.get("cumExecQty", "0")),
                        executed_price=Decimal(existing_order.get("avgPrice", "0") or "0"),
                        start_ms=start_ms,
                        retry_count=attempt
                    )
                    
            try:
                # 1. Place the main limit/market order
                # For demo purposes, we will assume a MARKET order if limit entry is not provided
                # Actually, TradePlan has entry, but let's just place a MARKET order to guarantee entry,
                # or LIMIT if we want to wait. Let's use MARKET since Bybit Demo supports it.
                order_result = await self._client.place_order(
                    symbol=plan.symbol,
                    side=plan.direction.value,
                    order_type="Market", # Can be modified later
                    qty=str(plan.qty),
                    order_link_id=client_order_id
                )
                
                exchange_order_id = order_result.get("result", {}).get("orderId")
                
                self._circuit.record_success()
                
                # 2. Wait briefly to allow fill, then set stops
                await asyncio.sleep(1.0)
                
                # Set stops
                # PositionIdx: 1 for Long, 2 for Short in Hedge Mode. 0 in One-Way Mode.
                # Assuming One-Way Mode for Demo (positionIdx=0)
                await self._client.set_trading_stop(
                    symbol=plan.symbol,
                    position_idx=0,
                    take_profit=str(plan.tp),
                    stop_loss=str(plan.sl)
                )
                
                return self._build_result(
                    status=ExecutionStatus.SUCCESS,
                    plan=plan,
                    client_order_id=client_order_id,
                    exchange_order_id=exchange_order_id,
                    executed_qty=plan.qty, # We assume full fill for Market order in Demo
                    executed_price=plan.entry,
                    start_ms=start_ms,
                    retry_count=attempt
                )
                
            except ExchangeAPIError as e:
                # Check error codes
                if e.ret_code in (10002, 10006): # Rate Limit
                    logger.warning(f"Rate limit hit. Backing off... Attempt {attempt}")
                    await asyncio.sleep(2 ** attempt)
                    attempt += 1
                elif e.ret_code in (130006, 130074, 110043, 10001): # Precision, Margin, Unsupported
                    self._circuit.record_failure()
                    return self._build_result(
                        status=ExecutionStatus.FAILED,
                        plan=plan,
                        client_order_id=client_order_id,
                        start_ms=start_ms,
                        retry_count=attempt,
                        error_code=str(e.ret_code),
                        error_message=e.message
                    )
                else:
                    self._circuit.record_failure()
                    # Unknown API error, retry
                    attempt += 1
                    await asyncio.sleep(1)
            except Exception as e:
                # Network Timeout
                logger.error(f"Network timeout / unknown error: {e}")
                self._circuit.record_failure()
                attempt += 1
                await asyncio.sleep(2)
                
        # If we exit the loop, we ran out of retries and we don't know the state
        return self._build_result(
            status=ExecutionStatus.UNKNOWN,
            plan=plan,
            client_order_id=client_order_id,
            start_ms=start_ms,
            retry_count=attempt,
            error_code="TIMEOUT",
            error_message="Max retries exceeded, status unknown."
        )
        
    def _build_result(
        self,
        status: ExecutionStatus,
        plan: TradePlan,
        client_order_id: str,
        start_ms: float,
        retry_count: int,
        exchange_order_id: str | None = None,
        executed_qty: Decimal = Decimal("0"),
        executed_price: Decimal = Decimal("0"),
        error_code: str | None = None,
        error_message: str | None = None
    ) -> ExecutionResult:
        
        now = time.time()
        end_ms = now * 1000
        
        return ExecutionResult(
            decision_id=plan.decision_id,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            status=status,
            executed_qty=executed_qty,
            executed_price=executed_price,
            submit_timestamp=start_ms / 1000.0,
            ack_timestamp=now,
            complete_timestamp=now,
            retry_count=retry_count,
            latency_ms=end_ms - start_ms,
            error_code=error_code,
            error_message=error_message
        )
