import pytest
import asyncio
from datetime import datetime, UTC
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from marketpilot.dashboard.server import lifespan
from marketpilot.config.settings import AppSettings

@pytest.mark.asyncio
async def test_dashboard_lifespan():
    """Verify Dashboard lifespan connects/disconnects public adapter."""
    app = FastAPI()
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.get_server_time = AsyncMock(return_value=datetime.now(UTC))
    mock_client.get_klines = AsyncMock(return_value=[])
    mock_client.get_tickers = AsyncMock(return_value=[])
    
    app.state.client_override = mock_client
    app.state.settings_override = AppSettings()
    
    # Run the lifespan async context manager
    async with lifespan(app):
        # Connected!
        mock_client.connect.assert_called_once()
        assert app.state.feed is not None
        
        # Give the feed task a moment to start
        await asyncio.sleep(0.1)
        assert app.state.feed.is_running is True
        
        # yield happens here
        
    # Disconnected and canceled feed
    mock_client.disconnect.assert_called_once()
    assert app.state.feed.is_running is False
