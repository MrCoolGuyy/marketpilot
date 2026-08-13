"""
MarketPilot Engines - Health Monitor.

Aggregates system health, latencies, and circuit breaker states into a single view.
"""

from typing import Any
from marketpilot.core.metrics_registry import MetricsRegistry
from marketpilot.engines.circuit_breaker import CircuitBreaker, SystemState

class HealthMonitor:
    def __init__(self, metrics: MetricsRegistry, circuit_breaker: CircuitBreaker):
        self.metrics = metrics
        self.cb = circuit_breaker
        
    def get_health_snapshot(self) -> dict[str, Any]:
        """Generates a comprehensive view of system health."""
        base_metrics = self.metrics.get_snapshot()
        
        status = "OK"
        if self.cb.state == SystemState.WARNING:
            status = "WARNING"
        elif self.cb.state == SystemState.HALTED:
            status = "CRITICAL"
            
        return {
            "status": status,
            "circuit_breaker_state": self.cb.state.name,
            "halt_reason": self.cb.halt_reason,
            "metrics": base_metrics
        }
