"""
MarketPilot Daemon - Scheduler.

Triggers pipeline cycles on a timer or cron basis.
"""

import asyncio
from typing import Callable, Coroutine, Any
from loguru import logger
from marketpilot.core.time_source import TimeSource

class Scheduler:
    def __init__(self, time_source: TimeSource, interval_seconds: float = 60.0):
        self.ts = time_source
        self.interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._callback: Callable[[], Coroutine[Any, Any, None]] | None = None
        self._is_running = False
        
    def set_callback(self, callback: Callable[[], Coroutine[Any, Any, None]]):
        self._callback = callback
        
    async def _loop(self):
        while self._is_running:
            if self._callback:
                try:
                    await self._callback()
                except Exception as e:
                    logger.error(f"Scheduler caught exception during cycle: {e}")
            await asyncio.sleep(self.interval)
            
    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"Scheduler started with {self.interval}s interval.")
        
    async def stop(self):
        """Stops the scheduler from emitting new ticks."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped.")
