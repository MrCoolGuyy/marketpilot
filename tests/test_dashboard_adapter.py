import pytest
from unittest.mock import AsyncMock, MagicMock
from marketpilot.exchange.public_adapter import PublicBybitMarketDataAdapter

@pytest.mark.asyncio
async def test_dashboard_adapter_read_only():
    """Prove that PublicBybitMarketDataAdapter only exposes safe methods and not place_order."""
    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    
    adapter = PublicBybitMarketDataAdapter(mock_client)
    
    # Prove safe methods exist
    assert hasattr(adapter, "get_server_time")
    assert hasattr(adapter, "get_klines")
    assert hasattr(adapter, "get_tickers")
    
    # Prove mutation methods DO NOT exist
    assert not hasattr(adapter, "place_order")
    assert not hasattr(adapter, "cancel_order")
    assert not hasattr(adapter, "amend_order")
    assert not hasattr(adapter, "set_trading_stop")
    assert not hasattr(adapter, "get_positions") # Sensitive
    
    await adapter.connect()
    mock_client.connect.assert_called_once()
    
    await adapter.disconnect()
    mock_client.disconnect.assert_called_once()
