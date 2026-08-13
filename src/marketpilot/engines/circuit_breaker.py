"""
MarketPilot Engines - Circuit Breaker.

A global system halt mechanism that triggers under abnormal conditions.
"""

from __future__ import annotations

from enum import Enum
import time

class SystemState(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    HALTED = "HALTED"

class CircuitBreaker:
    """Monitors system health and halts the pipeline if critical thresholds are breached."""
    
    def __init__(self):
        self.state: SystemState = SystemState.NORMAL
        
        # State tracking
        self.consecutive_failures = 0
        self.last_api_latency_ms = 0.0
        self.market_data_staleness_seconds = 0.0
        self.clock_drift_ms = 0.0
        
        self.halt_reason: str = ""
        
        # Config thresholds
        self.max_consecutive_failures = 5
        self.max_latency_ms = 2000.0
        self.max_staleness_seconds = 30.0
        self.max_clock_drift_ms = 1000.0

    def record_failure(self):
        self.consecutive_failures += 1
        self._evaluate()
        
    def record_success(self):
        self.consecutive_failures = 0
        if self.state == SystemState.WARNING:
            self.state = SystemState.NORMAL
            
    def update_metrics(self, latency_ms: float, staleness_sec: float, drift_ms: float):
        self.last_api_latency_ms = latency_ms
        self.market_data_staleness_seconds = staleness_sec
        self.clock_drift_ms = drift_ms
        self._evaluate()

    def _evaluate(self):
        if self.state == SystemState.HALTED:
            return # Requires manual intervention
            
        reasons = []
        
        if self.consecutive_failures >= self.max_consecutive_failures:
            reasons.append(f"{self.consecutive_failures} consecutive execution failures")
            
        if self.last_api_latency_ms > self.max_latency_ms:
            reasons.append(f"API latency ({self.last_api_latency_ms}ms) exceeds {self.max_latency_ms}ms")
            
        if self.market_data_staleness_seconds > self.max_staleness_seconds:
            reasons.append(f"Market data stale by {self.market_data_staleness_seconds}s")
            
        if self.clock_drift_ms > self.max_clock_drift_ms:
            reasons.append(f"Clock drift ({self.clock_drift_ms}ms) exceeds {self.max_clock_drift_ms}ms")
            
        if reasons:
            self.state = SystemState.HALTED
            self.halt_reason = " | ".join(reasons)
        elif self.consecutive_failures > 0 or self.last_api_latency_ms > (self.max_latency_ms * 0.8):
            self.state = SystemState.WARNING
            
    def assert_healthy(self):
        if self.state == SystemState.HALTED:
            raise RuntimeError(f"SYSTEM HALTED: {self.halt_reason}")

