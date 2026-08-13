"""
MarketPilot Engines - Watchdog.

Monitors the pipeline for hangs and triggers escalating alerts.
"""

import asyncio
from loguru import logger
from marketpilot.core.time_source import TimeSource
from marketpilot.engines.circuit_breaker import CircuitBreaker, SystemState

class Watchdog:
    """Escalating hang detection."""
    
    def __init__(self, time_source: TimeSource, circuit_breaker: CircuitBreaker):
        self.ts = time_source
        self.cb = circuit_breaker
        self.current_cycle_start: float | None = None
        self._task: asyncio.Task | None = None
        
    def start_cycle(self):
        self.current_cycle_start = self.ts.time()
        
    def end_cycle(self):
        self.current_cycle_start = None
        
    async def _monitor_loop(self):
        while True:
            await asyncio.sleep(5)
            if self.current_cycle_start is None:
                continue
                
            elapsed = self.ts.time() - self.current_cycle_start
            
            if elapsed > 90:
                logger.error(f"Watchdog: Cycle hung for {elapsed:.1f}s. Halting Circuit Breaker.")
                self.cb.state = SystemState.HALTED
                self.cb.halt_reason = "Watchdog detected pipeline hang (>90s)."
            elif elapsed > 60:
                logger.error(f"Watchdog: CRITICAL hang detected ({elapsed:.1f}s).")
            elif elapsed > 30:
                logger.warning(f"Watchdog: Slow cycle warning ({elapsed:.1f}s).")
                
    def start(self):
        self._task = asyncio.create_task(self._monitor_loop())
        
    def stop(self):
        if self._task:
            self._task.cancel()
