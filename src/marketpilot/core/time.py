"""
MarketPilot Core - Time and Boundary Semantics.

Authoritative exchange time abstraction and interval resolution logic.
"""

import calendar
from datetime import datetime, UTC
from typing import Optional
from pydantic import BaseModel, Field
from marketpilot.core.enums import Interval

class MarketObservationClock(BaseModel, frozen=True):
    """Authoritative time-source provenance for causality."""
    observed_at: float = Field(..., description="The synchronized/authoritative timestamp (seconds)")
    time_source: str = Field(..., description="The source of the time (e.g., 'BYBIT_SERVER_TIME')")
    provenance: str = Field(..., description="Synchronization details or offset metadata")

class CandleBoundaryResolver:
    """Canonical resolver for determining candle close boundaries."""
    
    @staticmethod
    def get_close_time(open_time_sec: float, interval: Interval) -> float:
        """
        Calculate the exact close timestamp (in seconds) for a given open_time and interval.
        """
        dt = datetime.fromtimestamp(open_time_sec, tz=UTC)
        
        # Standard fixed-minute intervals
        if interval in {Interval.M1, Interval.M3, Interval.M5, Interval.M15, Interval.M30, 
                        Interval.H1, Interval.H2, Interval.H4, Interval.H6, Interval.H12}:
            minutes = int(interval.value)
            return open_time_sec + (minutes * 60)
            
        # 1 Day (24 hours)
        elif interval == Interval.D1:
            return open_time_sec + 86400
            
        # 1 Week (7 days)
        elif interval == Interval.W1:
            return open_time_sec + (7 * 86400)
            
        # 1 Month (Calendar-aware)
        elif interval == Interval.MN1:
            # Find the number of days in the current month
            days_in_month = calendar.monthrange(dt.year, dt.month)[1]
            return open_time_sec + (days_in_month * 86400)
            
        raise ValueError(f"Unsupported interval for boundary resolution: {interval}")
        
    @staticmethod
    def is_closed(open_time_sec: float, interval: Interval, clock: MarketObservationClock) -> bool:
        """
        A candle is closed if the authoritative observation time is at or after its theoretical close boundary.
        """
        close_time = CandleBoundaryResolver.get_close_time(open_time_sec, interval)
        return clock.observed_at >= close_time
