"""
MarketPilot Core - Time Source Abstraction.

Provides a pluggable clock for deterministic testing and backtesting.
"""

import time
from datetime import datetime, UTC
from abc import ABC, abstractmethod

class TimeSource(ABC):
    @abstractmethod
    def now(self) -> datetime:
        pass
        
    @abstractmethod
    def time_ns(self) -> int:
        pass
        
    @abstractmethod
    def time(self) -> float:
        pass

class SystemClock(TimeSource):
    """Real-time system clock for production."""
    def now(self) -> datetime:
        return datetime.now(tz=UTC)
        
    def time_ns(self) -> int:
        return time.time_ns()
        
    def time(self) -> float:
        return time.time()

class MockClock(TimeSource):
    """Deterministic clock for testing."""
    def __init__(self, start_timestamp: float = 1700000000.0):
        self._current_time = start_timestamp
        
    def advance(self, seconds: float):
        self._current_time += seconds
        
    def now(self) -> datetime:
        return datetime.fromtimestamp(self._current_time, tz=UTC)
        
    def time_ns(self) -> int:
        return int(self._current_time * 1e9)
        
    def time(self) -> float:
        return self._current_time
