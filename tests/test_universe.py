import pytest
from unittest.mock import AsyncMock, patch

from marketpilot.config.settings import ExchangeSettings, AppSettings, ExecutionMode
from marketpilot.core.enums import AssetType
from marketpilot.exchange.bybit_client import BybitClient

@pytest.fixture
def test_settings():
    return ExchangeSettings(
        api_key="test_key",
        api_secret="test_secret",
        testnet=True,
    )

@pytest.mark.asyncio
async def test_universe_filtering(test_settings):
    client = BybitClient(exchange_settings=test_settings, execution_mode=ExecutionMode.PAPER)
    
    mock_response = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "contractType": "LinearPerpetual",
                    "settleCoin": "USDT",
                    "status": "Trading",
                    "lotSizeFilter": {},
                    "priceFilter": {},
                    "leverageFilter": {}
                },
                {
                    "symbol": "ETHUSDT",
                    "contractType": "InversePerpetual", # Should reject
                    "settleCoin": "USDT",
                    "status": "Trading",
                    "lotSizeFilter": {},
                    "priceFilter": {},
                    "leverageFilter": {}
                },
                {
                    "symbol": "SOLUSDC",
                    "contractType": "LinearPerpetual",
                    "settleCoin": "USDC", # Should reject
                    "status": "Trading",
                    "lotSizeFilter": {},
                    "priceFilter": {},
                    "leverageFilter": {}
                },
                {
                    "symbol": "XRPUSDT",
                    "contractType": "LinearPerpetual",
                    "settleCoin": "USDT",
                    "status": "Settling", # Should reject
                    "lotSizeFilter": {},
                    "priceFilter": {},
                    "leverageFilter": {}
                }
            ],
            "nextPageCursor": ""
        }
    }
    
    client._call = AsyncMock(return_value=mock_response)
    client._http = AsyncMock() # Need to bypass connection check
    
    instruments = await client.get_instruments(AssetType.LINEAR)
    
    assert len(instruments) == 1
    assert instruments[0].symbol == "BTCUSDT"
