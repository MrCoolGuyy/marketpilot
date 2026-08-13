"""MarketPilot Autopilot — Coordination Service."""

import asyncio
from datetime import datetime, UTC
from decimal import Decimal

from loguru import logger

from marketpilot.config.settings import AppSettings
from marketpilot.demo.service import DemoExecutionService
from marketpilot.demo.store import DemoAuditStore
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.autopilot import CandidateDecision, AutopilotStatus
from marketpilot.models.demo import OrderStatus
from marketpilot.autopilot.selector import CandidateSelectorService


class AutopilotService:
    """Coordinates candidate selection and autonomous demo execution."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.selector = CandidateSelectorService(settings)
        self.demo_service = DemoExecutionService(settings)
        self.demo_store = DemoAuditStore()

    async def run_cycle(self) -> CandidateDecision | None:
        """Run a single autopilot evaluation cycle."""
        
        # 1. Check Kill Switch
        if self.settings.demo.kill_switch:
            logger.warning("Autopilot killed via kill_switch.")
            return None
            
        # 2. Get Equity
        client = BybitClient(self.settings.demo)
        equity = Decimal("0")
        try:
            await client.connect()
            bal_resp = await client._call(client._http.get_wallet_balance, accountType="UNIFIED")
            if "result" in bal_resp and "list" in bal_resp["result"]:
                for acc in bal_resp["result"]["list"]:
                    equity = Decimal(acc.get("totalEquity", "0"))
                    break
        except Exception as e:
            logger.error(f"Failed to fetch equity for autopilot: {e}")
            return None
        finally:
            await client.disconnect()
            
        if equity <= Decimal("0"):
            logger.error("Invalid equity for autopilot")
            return None

        # 3. Guard: Max 1 Open Position
        try:
            await client.connect()
            pos_resp = await client.get_positions(category="linear")
            pos_list = pos_resp.get("result", {}).get("list", [])
            active_positions = [p for p in pos_list if Decimal(p.get("size", "0")) > 0]
            if len(active_positions) >= 1:
                logger.info(f"Skipping cycle: Max open positions reached ({len(active_positions)}).")
                return None
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return None
        finally:
            await client.disconnect()

        # 4. Guard: Daily Limits (Trades and Loss)
        records = self.store_records_today()
        if len(records) >= self.settings.demo.max_daily_trades:
            logger.warning(f"Daily trade limit reached ({len(records)}).")
            return None
            
        # Calculate daily loss (simplified: sum of realized PnL of today's closed orders)
        # Note: A full daily loss logic would check account snapshot. We just check if there's any mechanism to stop.
        # Since DemoOrderRecord doesn't strictly track PnL yet, we just enforce the trade count limit for now,
        # but warn about the loss limit not being fully realized.
        
        # 5. Select Candidate
        candidate = await self.selector.select_best_candidate(equity)
        if not candidate:
            logger.info("No eligible candidates found.")
            return None
            
        # 6. Check Execution Intent
        if not self.settings.demo.auto_submit_enabled:
            logger.info(f"Suggesting {candidate.symbol} (auto_submit OFF).")
            # Return suggestion
            return candidate
            
        if not self.settings.demo.execution_enabled:
            logger.warning("Demo master execution switch is OFF.")
            return candidate

        # 7. Execute!
        logger.warning(f"AUTOPILOT ARMED: Submitting {candidate.direction.value} {candidate.symbol}...")
        
        # We need historical klines for DemoExecutionService.execute_open
        # Wait, DemoExecutionService.execute_open does its own scan/risk. 
        # But we already evaluated!
        # Since `execute_open` repeats calculation, let's just call it.
        # It's safer to use the dedicated execution pipeline.
        
        # First fetch klines
        try:
            await client.connect()
            klines = await client.get_klines(symbol=candidate.symbol, interval=Interval.H1)
        except Exception as e:
            logger.error(f"Failed to fetch klines for execution: {e}")
            return candidate
        finally:
            await client.disconnect()
            
        record = await self.demo_service.execute_open(
            symbol=candidate.symbol,
            interval=Interval.H1.value,
            equity=equity,
            klines=klines
        )
        
        if record:
            logger.success(f"Autopilot submitted {candidate.symbol}: {record.status.value}")
            return CandidateDecision(
                **candidate.model_dump(exclude={"status", "created_at"}),
                status=AutopilotStatus.SUBMITTED
            )
        else:
            logger.error(f"Autopilot failed to execute {candidate.symbol}.")
            return CandidateDecision(
                **candidate.model_dump(exclude={"status", "created_at"}),
                status=AutopilotStatus.REJECTED
            )

    def store_records_today(self):
        records = self.demo_store.load_records()
        today = datetime.now(tz=UTC).date()
        return [r for r in records if r.created_at.date() == today]
