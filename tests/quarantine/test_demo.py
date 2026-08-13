import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from pydantic import SecretStr

from marketpilot.config.settings import AppSettings, DemoSettings
from marketpilot.core.enums import EnvironmentProfile, OrderSide
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.demo.service import DemoExecutionService

@pytest.fixture
def mock_demo_settings():
    return AppSettings(
        app_name="MarketPilot",
        debug=False,
        demo=DemoSettings(
            profile=EnvironmentProfile.DEMO,
            api_key=SecretStr("DEMO_KEY"),
            api_secret=SecretStr("DEMO_SECRET"),
            execution_enabled=True
        )
    )

@pytest.fixture
def mock_mainnet_settings():
    return AppSettings(
        app_name="MarketPilot",
        debug=False,
        demo=DemoSettings(
            profile=EnvironmentProfile.MAINNET,
            api_key=SecretStr("MAINNET_KEY"),
            api_secret=SecretStr("MAINNET_SECRET"),
            execution_enabled=True
        )
    )
    
@pytest.fixture
def mock_disabled_settings():
    return AppSettings(
        app_name="MarketPilot",
        debug=False,
        demo=DemoSettings(
            profile=EnvironmentProfile.DEMO,
            api_key=SecretStr("DEMO_KEY"),
            api_secret=SecretStr("DEMO_SECRET"),
            execution_enabled=False
        )
    )

@pytest.mark.asyncio
async def test_mainnet_hard_block(mock_mainnet_settings, monkeypatch):
    client = BybitClient(mock_mainnet_settings.demo)
    
    mock_http = MagicMock()
    monkeypatch.setattr(client, "_http", mock_http)
    
    with pytest.raises(RuntimeError, match="CRITICAL: Mainnet/Testnet execution is strictly disabled. Use Demo only."):
        await client.place_order(symbol="BTCUSDT", side="Buy", order_type="Market", qty="0.1", order_link_id="123")

@pytest.mark.asyncio
async def test_demo_execution_disabled_switch(mock_disabled_settings, monkeypatch):
    service = DemoExecutionService(mock_disabled_settings)
    
    # Execution should abort silently and return None if disabled
    record = await service.execute_close("BTCUSDT", Decimal("0.1"))
    assert record is None

@pytest.mark.asyncio
async def test_demo_execution_success(mock_demo_settings, monkeypatch):
    service = DemoExecutionService(mock_demo_settings)
    
    # Mock BybitClient methods
    mock_client_instance = AsyncMock()
    mock_client_instance.place_order.return_value = {"retCode": 0, "result": {"orderId": "123"}}
    mock_client_instance.get_positions.return_value = {"result": {"list": [{"size": "0.1", "side": "Buy"}]}}
    mock_client_instance.get_order_status.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {
                    "orderId": "123",
                    "orderStatus": "Filled",
                    "cumExecQty": "0.1",
                    "avgPrice": "50000"
                }
            ]
        }
    }
    
    # Mock the BybitClient class instantiation
    monkeypatch.setattr("marketpilot.demo.service.BybitClient", lambda s: mock_client_instance)
    
    # Mock the store so we don't write to real file
    mock_store = MagicMock()
    mock_store.load_records.return_value = []
    service.store = mock_store
    
    record = await service.execute_close("BTCUSDT", Decimal("0.1"))
    
    assert record is not None
    assert record.symbol == "BTCUSDT"
    assert record.side == OrderSide.SELL
    assert record.quantity == Decimal("0.1")
    assert record.filled_quantity == Decimal("0.1")
    assert record.avg_fill_price == Decimal("50000")
    
    # Assert place_order was called with correct parameters
    mock_client_instance.place_order.assert_called_once()
    call_kwargs = mock_client_instance.place_order.call_args.kwargs
    assert call_kwargs["symbol"] == "BTCUSDT"
    assert call_kwargs["side"] == "Sell"
    assert call_kwargs["qty"] == "0.1"
    assert "order_link_id" in call_kwargs
    assert call_kwargs["order_link_id"] == record.order_link_id
