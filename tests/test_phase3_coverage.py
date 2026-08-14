import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch

from marketpilot.exchange.verifier import PositionModeVerifier, VerificationStatus
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.daemon.service import MissionControlDaemon
from marketpilot.config.settings import AppSettings, ExchangeSettings
from marketpilot.core.enums import MarketDataEnvironment, ExecutionMode

@pytest.mark.asyncio
async def test_verified_one_way_symbol():
    client = AsyncMock()
    # positionIdx 0 means one-way mode
    client.get_positions.return_value = {"result": {"list": [{"positionIdx": 0}]}}
    verifier = PositionModeVerifier(client)
    status = await verifier.verify_symbol("BTCUSDT")
    assert status == VerificationStatus.VERIFIED_ONE_WAY
    
@pytest.mark.asyncio
async def test_hedge_symbol():
    client = AsyncMock()
    # positionIdx 1 or 2 means hedge mode
    client.get_positions.return_value = {"result": {"list": [{"positionIdx": 1}, {"positionIdx": 2}]}}
    verifier = PositionModeVerifier(client)
    status = await verifier.verify_symbol("ETHUSDT")
    assert status == VerificationStatus.INCOMPATIBLE_HEDGE

@pytest.mark.asyncio
async def test_unverified_symbol():
    client = AsyncMock()
    # Empty list
    client.get_positions.return_value = {"result": {"list": []}}
    verifier = PositionModeVerifier(client)
    status = await verifier.verify_symbol("UNKNOWN")
    assert status == VerificationStatus.UNVERIFIED

@pytest.mark.asyncio
async def test_multipage_instrument_universe_and_later_page_retained():
    settings = ExchangeSettings(_env_file=None)
    client = BybitClient(exchange_settings=settings, execution_mode=ExecutionMode.PAPER)
    client._http = MagicMock()
    
    # Mock a 2-page response where page 2 has our eligible symbol
    client._http.get_instruments_info.side_effect = [
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [{"symbol": "BTCUSDT", "contractType": "Inverse", "settleCoin": "BTC", "status": "Trading"}], # Invalid v1
                "nextPageCursor": "page2",
            },
        },
        {
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "category": "linear",
                "list": [{"symbol": "ETHUSDT", "contractType": "LinearPerpetual", "settleCoin": "USDT", "status": "Trading"}], # Valid v1
                "nextPageCursor": "",
            },
        },
    ]
    
    from marketpilot.core.enums import AssetType
    instruments = await client.get_instruments(AssetType.LINEAR)
    assert len(instruments) == 1
    assert instruments[0].symbol == "ETHUSDT"

@pytest.mark.asyncio
async def test_regular_and_conditional_linear_order_recovery():
    settings = ExchangeSettings(_env_file=None)
    client = BybitClient(exchange_settings=settings, execution_mode=ExecutionMode.PAPER)
    client._http = MagicMock()
    
    # Return different orders in one unfiltered call
    def mock_get_open_orders(**kwargs):
        filter_type = kwargs.get("orderFilter")
        assert filter_type is None, "Linear active-order recovery must be an unfiltered superset"
        return {
            "result": {
                "list": [
                    {"orderId": "reg-1", "stopOrderType": ""}, 
                    {"orderId": "cond-1", "stopOrderType": "StopLoss"},
                    {"orderId": "cond-2", "stopOrderType": "TakeProfit"}
                ], 
                "nextPageCursor": ""
            }, 
            "retCode": 0
        }
        
    client._http.get_open_orders = MagicMock(side_effect=mock_get_open_orders)
    
    orders = await client.get_active_orders()
    order_ids = {o["orderId"] for o in orders}
    assert order_ids == {"reg-1", "cond-1", "cond-2"}
    # Spot tpslOrder must not be in the mock logic

@pytest.mark.asyncio
async def test_multiple_executions_for_one_order():
    settings = ExchangeSettings(_env_file=None)
    client = BybitClient(exchange_settings=settings, execution_mode=ExecutionMode.PAPER)
    client._http = MagicMock()
    
    client._http.get_executions.return_value = {
        "retCode": 0,
        "result": {
            "list": [
                {"execId": "ex-1", "orderId": "ord-1", "execQty": "0.1"},
                {"execId": "ex-2", "orderId": "ord-1", "execQty": "0.2"},
            ]
        }
    }
    execs = await client.get_execution_history()
    assert len(execs["list"]) == 2
    assert execs["list"][0]["orderId"] == "ord-1"
    assert execs["list"][1]["orderId"] == "ord-1"

@pytest.mark.asyncio
async def test_order_history_pagination_and_cyclic_cursor():
    settings = AppSettings()
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        
        client = AsyncMock()
        client.get_active_orders = AsyncMock(return_value=[])
        client.get_positions = AsyncMock(return_value={"result": {"list": []}})
        
        # Mock cyclic cursor behavior
        async def mock_history(**kwargs):
            return {"list": [{"orderId": "123", "orderLinkId": "dec-1"}], "nextPageCursor": "cycle"}
            
        client.get_order_history = mock_history
        ctx.client = client
        ctx.journal = MagicMock()
        ctx.journal.get_active_decision_ids.return_value = ["dec-unresolved"] # Ensure loop continues
        
        mock_build.return_value = ctx
        daemon = MissionControlDaemon()
        daemon._shutdown_event = AsyncMock()
        
        # run startup recovery, expect it to hit the cyclic cursor trap and return False (UNSAFE)
        result = await daemon._perform_startup_recovery()
        assert result is False

@pytest.mark.asyncio
async def test_insufficient_history_unsafe():
    settings = AppSettings()
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        
        client = AsyncMock()
        client.get_active_orders = AsyncMock(return_value=[])
        client.get_positions = AsyncMock(return_value={"result": {"list": []}})
        
        # Return finite history but missing the required decision
        client.get_order_history = AsyncMock(return_value={"list": [{"orderId": "123", "orderLinkId": "dec-1"}], "nextPageCursor": ""})
        client.get_execution_history = AsyncMock(return_value={"list": [], "nextPageCursor": ""})
        ctx.client = client
        ctx.journal = MagicMock()
        ctx.journal.get_active_decision_ids.return_value = ["dec-required"]
        
        mock_build.return_value = ctx
        daemon = MissionControlDaemon()
        daemon._shutdown_event = MagicMock()
        
        result = await daemon._perform_startup_recovery()
        assert result is False

def test_mainnet_market_data_paper_execution_semantics():
    settings = AppSettings(_env_file=None)
    assert settings.exchange.environment == MarketDataEnvironment.MAINNET
    assert settings.execution_mode == ExecutionMode.PAPER

@pytest.mark.asyncio
async def test_execution_history_pagination():
    settings = AppSettings()
    with patch("marketpilot.core.factory.MissionControlFactory.build_runtime") as mock_build:
        ctx = MagicMock()
        ctx.settings = settings
        
        client = AsyncMock()
        client.get_active_orders = AsyncMock(return_value=[])
        client.get_positions = AsyncMock(return_value={"result": {"list": []}})
        
        # Order history is complete in page 1 but missing executions
        client.get_order_history = AsyncMock(return_value={"list": [{"orderId": "123", "orderLinkId": "dec-1"}], "nextPageCursor": ""})
        
        # Page 1 returns ex-1 and nextPageCursor, missing required decision
        # Page 2 returns ex-2 with required decision and no cursor
        async def mock_get_executions(**kwargs):
            cursor = kwargs.get("cursor")
            if not cursor:
                return {
                    "list": [{"execId": "ex-1", "orderId": "123", "execQty": "0.1", "orderLinkId": "dec-other"}],
                    "nextPageCursor": "page2"
                }
            elif cursor == "page2":
                return {
                    "list": [{"execId": "ex-2", "orderId": "123", "execQty": "0.2", "orderLinkId": "dec-required"}],
                    "nextPageCursor": ""
                }
            return {"list": []}
            
        client.get_execution_history = mock_get_executions
        
        ctx.client = client
        ctx.journal = MagicMock()
        ctx.journal.get_active_decision_ids.return_value = ["dec-1", "dec-required"]
        ctx.exposure = MagicMock() 
        
        mock_build.return_value = ctx
        daemon = MissionControlDaemon()
        daemon._shutdown_event = AsyncMock()
        
        # Since it successfully resolves dec-1 via order_history and dec-required via execution_history page 2,
        # it should pass the safety check (assuming reconciler doesn't fail it for other reasons).
        # We just want to ensure it doesn't raise the "Unresolved lineage" error and actually hits reconcile.
        daemon.reconciler = MagicMock()
        mock_res = MagicMock()
        mock_res.success = True
        daemon.reconciler.reconcile_startup.return_value = mock_res
        
        result = await daemon._perform_startup_recovery()
        assert result is True
        
        # Ensure reconcile was called with the execution dict containing both execs
        call_args = daemon.reconciler.reconcile_startup.call_args[0]
        execution_dict = call_args[4]
        assert "ex-1" in execution_dict
        assert "ex-2" in execution_dict
