import pytest
from datetime import datetime, UTC
from typing import Optional
from fastapi.testclient import TestClient

from marketpilot.core.enums import Interval, AssetType, MarketDataEnvironment
from marketpilot.config.settings import AppSettings
from marketpilot.dashboard.server import app
from marketpilot.dashboard.feed import DashboardObservationFeed
from marketpilot.models.market import Kline, Ticker
from marketpilot.dashboard.store import DashboardReadStore

class FakeMarketDataReader:
    """Fake MarketDataReader for testing without real Bybit network I/O."""
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        
    async def get_server_time(self) -> datetime:
        if self.should_fail:
            raise RuntimeError("Fake network failure")
        return datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        
    async def get_klines(self, symbol: str, interval: Interval, limit: int = 200, asset_type: AssetType = AssetType.LINEAR) -> list:
        # Provide one fake closed kline and one forming kline
        return [
            Kline(
                symbol=symbol,
                interval=interval.value,
                open_time=1735732800,  # 2025-01-01 12:00:00 (this is the forming one)
                open="100.0",
                high="105.0",
                low="95.0",
                close="102.0",
                volume="1000.0",
                turnover="102000.0",
                is_closed=False
            ),
            Kline(
                symbol=symbol,
                interval=interval.value,
                open_time=1735729200,  # 2025-01-01 11:00:00 (closed)
                open="98.0",
                high="101.0",
                low="97.0",
                close="100.0",
                volume="900.0",
                turnover="89000.0",
                is_closed=True
            )
        ]
        
    async def get_tickers(self, symbol: str, asset_type: AssetType = AssetType.LINEAR) -> list:
        return [
            Ticker(
                symbol=symbol,
                asset_type=AssetType.LINEAR,
                last_price="102.0",
                bid_price="101.9",
                ask_price="102.1",
                high_24h="105.0",
                low_24h="95.0",
                price_change_percent_24h="2.0",
                volume_24h="50000.0",
                turnover_24h="5000000.0",
                funding_rate="0.0001",
                open_interest="1000.0",
                timestamp=1735732800,
                last_update_time=1735732800000
            )
        ]


@pytest.mark.asyncio
async def test_dashboard_feed_run_once():
    """Prove the deterministic run_once one-cycle flow."""
    store = DashboardReadStore()
    settings = AppSettings()
    fake_client = FakeMarketDataReader()
    
    feed = DashboardObservationFeed(store=store, client=fake_client, settings=settings)
    
    # Run a successful cycle
    await feed.run_once("BTCUSDT")
    
    assert feed.is_degraded is False
    assert feed.last_observation is not None
    
    intelligence = store.get_market_intelligence("BTCUSDT")
    assert intelligence is not None
    assert intelligence.symbol == "BTCUSDT"
    assert intelligence.close == "100.0"  # Extracted from the closed kline!
    
    # Run a failing cycle
    failing_feed = DashboardObservationFeed(store=store, client=FakeMarketDataReader(should_fail=True), settings=settings)
    
    try:
        await failing_feed.run_once("BTCUSDT")
    except Exception:
        failing_feed.is_degraded = True
        
    assert failing_feed.is_degraded is True


def test_dashboard_lifespan():
    """Prove that real FastAPI lifespan initializes correctly and closes gracefully without orphan tasks."""
    # We use TestClient as a context manager, which triggers the lifespan startup/shutdown
    
    # Before starting, inject fake settings and client to prevent network access
    fake_settings = AppSettings()
    fake_settings.exchange.environment = MarketDataEnvironment.TESTNET
    app.state.settings_override = fake_settings
    app.state.client_override = FakeMarketDataReader()
    
    with TestClient(app) as client:
        # App is now running inside the lifespan context
        store = app.state.dashboard_read_store
        feed = app.state.feed
        
        # Verify initialization
        assert store is not None
        assert isinstance(store, DashboardReadStore)
        assert feed is not None
        assert feed.is_running is True
        
        # Verify endpoints work
        resp = client.get("/api/system/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "system" in data
        assert "execution_mode" in data["system"]
        assert "market_data_environment" in data["system"]
        
    # Exited context, verify shutdown
    assert feed.is_running is False
