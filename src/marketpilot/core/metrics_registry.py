"""
MarketPilot Core - Metrics Registry.

Single source of truth for component health and performance metrics.
"""

from collections import defaultdict
from typing import Any
import time

class MetricsRegistry:
    def __init__(self):
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)
        
    def record_latency(self, component: str, latency_ms: float):
        # Keep last 100 for percentile calculation to avoid memory leak
        if len(self._latencies[component]) >= 100:
            self._latencies[component].pop(0)
        self._latencies[component].append(latency_ms)
        
    def increment(self, counter_name: str, value: int = 1):
        self._counters[counter_name] += value
        
    def set_gauge(self, gauge_name: str, value: float):
        self._gauges[gauge_name] = value
        
    def get_snapshot(self) -> dict[str, Any]:
        snapshot = {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "latencies": {}
        }
        
        for component, lats in self._latencies.items():
            if not lats:
                continue
            avg = sum(lats) / len(lats)
            sorted_lats = sorted(lats)
            p95_idx = int(len(sorted_lats) * 0.95)
            p95 = sorted_lats[p95_idx]
            snapshot["latencies"][component] = {
                "average_ms": round(avg, 2),
                "p95_ms": round(p95, 2),
                "samples": len(lats)
            }
            
        return snapshot
