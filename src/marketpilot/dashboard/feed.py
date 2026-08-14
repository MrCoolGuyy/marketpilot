"""
MarketPilot Dashboard - Read-Only Observation Feed.

A safe, background feed for pulling MAINNET data and updating the DashboardReadStore
without injecting mutation capabilities into the Mission Control runtime.
"""

import asyncio
import logging
from datetime import datetime

from marketpilot.core.enums import Interval, AssetType
from marketpilot.config.settings import AppSettings
from marketpilot.dashboard.store import DashboardReadStore, DashboardProjection
from marketpilot.scanner.snapshot_builder import InstrumentSnapshotBuilder
from marketpilot.engines.indicator_engine import IndicatorEngine
from marketpilot.models.market_data import RawMarketData
from marketpilot.core.time import MarketObservationClock
from typing import Protocol, List

logger = logging.getLogger("marketpilot.dashboard.feed")

class MarketDataReader(Protocol):
    """Strict read-only capability for market data observation."""
    async def get_server_time(self) -> datetime: ...
    async def get_klines(self, symbol: str, interval: Interval, limit: int = 200, asset_type: AssetType = AssetType.LINEAR) -> list: ...
    async def get_tickers(self, symbol: str, asset_type: AssetType = AssetType.LINEAR) -> list: ...

class DashboardObservationFeed:
    """A strictly read-only feed for populating the DashboardReadStore."""
    
    def __init__(self, store: DashboardReadStore, client: MarketDataReader, settings: AppSettings):
        self.store = store
        self.client = client
        self.settings = settings
        self.is_running = False
        self.last_observation: datetime | None = None
        self.is_degraded = False
        
    async def run_once(self, symbol: str) -> None:
        """Execute a single observation cycle deterministically."""
        # 1. Authoritative server time
        server_time = await self.client.get_server_time()
        server_time_sec = server_time.timestamp()
        
        # 2. Canonical Clock
        clock = MarketObservationClock(
            observed_at=server_time_sec,
            time_source="BYBIT_SERVER_TIME",
            provenance="MAINNET_REST"
        )
        
        # 3. Raw Klines & Ticker
        klines = await self.client.get_klines(
            symbol=symbol,
            interval=Interval.H1,
            limit=200,
            asset_type=AssetType.LINEAR
        )
        tickers = await self.client.get_tickers(symbol=symbol, asset_type=AssetType.LINEAR)
        ticker = tickers[0] if tickers else None
        
        if klines and ticker:
            # 4. Forming exclusion & ClosedInstrumentSnapshot (handled by builder)
            builder = InstrumentSnapshotBuilder(IndicatorEngine(self.settings.indicators))
            
            raw = RawMarketData(
                symbol=symbol,
                asset_type=AssetType.LINEAR,
                ticker=ticker,
                klines=klines,
                timestamp=server_time_sec
            )
            
            result = builder.build_causal(
                raw=raw,
                clock=clock
            )
            
            snapshot = result.snapshot
            if snapshot:
                # 5. Market Intelligence projection
                intelligence = DashboardProjection.project_market_intelligence(snapshot)
                
                # 6. DashboardReadStore in-memory publication
                self.store.publish_market_observation([intelligence])
                
                self.last_observation = server_time
                self.is_degraded = False

    async def run_loop(self):
        """Main observation loop to update DashboardReadStore."""
        self.is_running = True
        logger.info("Dashboard Observation Feed started.")
        
        while self.is_running:
            try:
                # Use a specific symbol or loop through configured assets
                symbol = "BTCUSDT"
                await self.run_once(symbol)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Observation feed error: {e}")
                self.is_degraded = True
                
            # Sleep until next interval (hardcoded cadence for dashboard updates)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
                
        logger.info("Dashboard Observation Feed stopped.")
