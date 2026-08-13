"""MarketPilot Demo — Execution Service."""

import asyncio
from datetime import datetime, UTC
from decimal import Decimal
from typing import Sequence
from uuid import uuid4

from loguru import logger

from marketpilot.config.settings import AppSettings
from marketpilot.core.enums import OrderSide, OrderType, OrderStatus, EnvironmentProfile
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.indicators.service import IndicatorService
from marketpilot.models.demo import DemoOrderRecord
from marketpilot.models.market import Kline
from marketpilot.demo.store import DemoAuditStore
from marketpilot.risk.service import RiskManagerService
from marketpilot.strategy.service import StrategyService
from marketpilot.models.strategy import SignalDirection

class DemoExecutionService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.store = DemoAuditStore()
        
    async def execute_open(self, symbol: str, interval: str, equity: Decimal, klines: Sequence[Kline]) -> DemoOrderRecord | None:
        """Evaluate strictly historical klines and place an order if eligible."""
        if not self.settings.demo.execution_enabled:
            logger.error("Demo execution is disabled in settings.")
            return None
            
        if self.settings.demo.profile != EnvironmentProfile.DEMO:
            logger.error(f"Cannot execute demo order under {self.settings.demo.profile.value} profile.")
            return None
            
        if not klines:
            return None
            
        valid_klines = [k for k in klines if k.is_closed]
        valid_klines.sort(key=lambda k: k.open_time)
        
        if not valid_klines:
            return None
            
        ind_service = IndicatorService(self.settings.indicators)
        series = ind_service.calculate(valid_klines)
        
        strat_service = StrategyService(self.settings.strategy)
        signal = strat_service.evaluate(series)
        
        if signal.direction not in (SignalDirection.LONG, SignalDirection.SHORT):
            logger.warning("No actionable signal generated.")
            return None
            
        client = BybitClient(self.settings.demo)
        
        try:
            await client.connect()
            
            # Fetch instrument info for rounding
            instrument_info = await client.get_instruments_info(symbol)
            
            # Fetch live ticker for actual execution price
            tickers = await client.get_tickers(symbol)
            if not tickers:
                logger.error(f"Could not fetch live ticker for {symbol}")
                return None
                
            ticker = tickers[0]
            if signal.direction == SignalDirection.LONG:
                entry_price = ticker.ask_price
            else:
                entry_price = ticker.bid_price
                
            if not entry_price or entry_price <= Decimal("0"):
                logger.error(f"Invalid live entry price: {entry_price}")
                return None
                
            risk_service = RiskManagerService(self.settings.risk)
            atr_series = [p for p in series if p.atr is not None]
            if not atr_series:
                logger.error("No ATR data available for risk assessment")
                return None
                
            atr = atr_series[-1].atr
            
            assessment = risk_service.assess(
                signal=signal,
                entry_price=entry_price,
                atr=atr,
                account_equity=equity
            )
            
            if not assessment.eligible_for_paper_trading or assessment.theoretical_quantity is None:
                logger.warning(f"Risk assessment failed eligibility: {assessment.reasons}")
                return None
                
            # Round quantity to nearest qty_step
            raw_qty = assessment.theoretical_quantity
            qty_step = instrument_info.qty_step
            rounded_qty = (raw_qty // qty_step) * qty_step
            
            if rounded_qty < instrument_info.min_qty:
                logger.warning(f"Quantity {rounded_qty} below min_qty {instrument_info.min_qty}")
                return None
            if rounded_qty > instrument_info.max_qty:
                logger.warning(f"Quantity {rounded_qty} above max_qty {instrument_info.max_qty}")
                rounded_qty = instrument_info.max_qty
                
            if rounded_qty <= Decimal("0"):
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch market data or assess risk: {e}")
            return None
        finally:
            await client.disconnect()
            
        side = OrderSide.BUY if signal.direction == SignalDirection.LONG else OrderSide.SELL
        order_link_id = uuid4().hex

        
        # Create record immediately to ensure idempotency tracking
        record = DemoOrderRecord(
            order_link_id=order_link_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=rounded_qty,
            price=None,
            status=OrderStatus.NEW,
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            risk_snapshot=assessment.model_dump(mode="json")
        )
        
        records = self.store.load_records()
        records.append(record)
        self.store.save_records(records)
        
        try:
            await client.connect()
            resp = await client.place_order(
                symbol=symbol,
                side=side.value,
                order_type=OrderType.MARKET.value,
                qty=str(rounded_qty),
                order_link_id=order_link_id
            )
            
            # Sanitize response
            safe_resp = {
                "retCode": resp.get("retCode"),
                "retMsg": resp.get("retMsg"),
                "orderId": resp.get("result", {}).get("orderId"),
                "orderLinkId": resp.get("result", {}).get("orderLinkId")
            }
            record.raw_response = safe_resp
            
            # Poll status with timeout limit
            record.status = OrderStatus.NEW
            for _ in range(3):
                await asyncio.sleep(1.0)
                status_resp = await client.get_order_status(symbol=symbol, order_link_id=order_link_id)
                
                if "result" in status_resp and "list" in status_resp["result"] and status_resp["result"]["list"]:
                    order_data = status_resp["result"]["list"][0]
                    record.order_id = order_data.get("orderId", "")
                    
                    status_str = order_data.get("orderStatus", "")
                    try:
                        parsed_status = OrderStatus(status_str)
                        record.status = parsed_status
                    except ValueError:
                        pass
                        
                    record.filled_quantity = Decimal(order_data.get("cumExecQty", "0"))
                    avg_price = order_data.get("avgPrice", "")
                    if avg_price:
                        record.avg_fill_price = Decimal(avg_price)
                        
                    if record.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                        break
                        
            # Set SL/TP if order is active
            if record.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED) and record.order_id:
                try:
                    await client.set_trading_stop(
                        symbol=symbol,
                        position_idx=0,  # Default OneWay mode for USDT Linear
                        take_profit=str(assessment.take_profit) if assessment.take_profit else None,
                        stop_loss=str(assessment.stop_loss) if assessment.stop_loss else None,
                    )
                except Exception as e:
                    logger.error(f"Failed to set SL/TP for {symbol}: {e}")
                    # Keep status UNPROTECTED or just append a flag
                    if record.status == OrderStatus.FILLED:
                        record.status = OrderStatus.UNPROTECTED
                        
            record.updated_at = datetime.now(tz=UTC)
            self.store.save_records(records)
            return record
            
        except Exception as e:
            logger.error(f"Demo execution failed: {e}")
            record.status = OrderStatus.REJECTED
            record.updated_at = datetime.now(tz=UTC)
            self.store.save_records(records)
            return record
        finally:
            await client.disconnect()

    async def execute_close(self, symbol: str, quantity: Decimal | None = None) -> DemoOrderRecord | None:
        """Close an existing demo position manually."""
        if not self.settings.demo.execution_enabled:
            logger.error("Demo execution is disabled in settings.")
            return None
            
        if self.settings.demo.profile != EnvironmentProfile.DEMO:
            logger.error(f"Cannot execute demo order under {self.settings.demo.profile.value} profile.")
            return None
            
        record = None
        client = BybitClient(self.settings.demo)
        try:
            await client.connect()
            
            # Query actual demo positions
            pos_resp = await client.get_positions(symbol=symbol)
            pos_list = pos_resp.get("result", {}).get("list", [])
            
            # Filter active positions
            active_positions = [p for p in pos_list if Decimal(p.get("size", "0")) > 0]
            
            if not active_positions:
                logger.error(f"No active positions found for {symbol}")
                return None
                
            if len(active_positions) > 1:
                logger.error(f"Ambiguous hedge position found for {symbol}. Cannot automatically close.")
                return None
                
            pos = active_positions[0]
            pos_size = Decimal(pos.get("size", "0"))
            pos_side = pos.get("side", "")
            
            if pos_side.lower() == "buy":
                side = OrderSide.SELL
            elif pos_side.lower() == "sell":
                side = OrderSide.BUY
            else:
                logger.error(f"Unknown position side {pos_side}")
                return None
                
            close_qty = quantity if quantity is not None else pos_size
            if close_qty > pos_size:
                logger.error(f"Requested close quantity {close_qty} exceeds open position size {pos_size}")
                return None
            if close_qty <= Decimal("0"):
                return None

            order_link_id = uuid4().hex
            
            record = DemoOrderRecord(
                order_link_id=order_link_id,
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=close_qty,
                status=OrderStatus.NEW,
                created_at=datetime.now(tz=UTC),
                updated_at=datetime.now(tz=UTC)
            )
            
            records = self.store.load_records()
            records.append(record)
            self.store.save_records(records)

            resp = await client.place_order(
                symbol=symbol,
                side=side.value,
                order_type=OrderType.MARKET.value,
                qty=str(close_qty),
                order_link_id=order_link_id,
                reduce_only=True
            )
            
            # Sanitize response
            safe_resp = {
                "retCode": resp.get("retCode"),
                "retMsg": resp.get("retMsg"),
                "orderId": resp.get("result", {}).get("orderId"),
                "orderLinkId": resp.get("result", {}).get("orderLinkId")
            }
            record.raw_response = safe_resp
            
            # Poll status with timeout limit
            record.status = OrderStatus.NEW
            for _ in range(3):
                await asyncio.sleep(1.0)
                status_resp = await client.get_order_status(symbol=symbol, order_link_id=order_link_id)
                
                if "result" in status_resp and "list" in status_resp["result"] and status_resp["result"]["list"]:
                    order_data = status_resp["result"]["list"][0]
                    record.order_id = order_data.get("orderId", "")
                    status_str = order_data.get("orderStatus", "")
                    try:
                        record.status = OrderStatus(status_str)
                    except ValueError:
                        pass
                    record.filled_quantity = Decimal(order_data.get("cumExecQty", "0"))
                    avg_price = order_data.get("avgPrice", "")
                    if avg_price:
                        record.avg_fill_price = Decimal(avg_price)
                        
                    if record.status in (OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
                        break
                        
            record.updated_at = datetime.now(tz=UTC)
            self.store.save_records(records)
            return record
            
        except Exception as e:
            logger.error(f"Demo close execution failed: {e}")
            if record is not None:
                record.status = OrderStatus.REJECTED
                record.updated_at = datetime.now(tz=UTC)
                
                # We need to reload records to save since we might be out of sync
                records = self.store.load_records()
                # Find and update
                for i, r in enumerate(records):
                    if r.order_link_id == record.order_link_id:
                        records[i] = record
                        break
                self.store.save_records(records)
                return record
            return None
        finally:
            await client.disconnect()
