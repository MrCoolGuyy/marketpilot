"""
Tests for the Bybit exchange client.

All tests use mocked pybit HTTP responses — no real API calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from marketpilot.config.settings import ExchangeSettings, AppSettings, ExecutionMode
from marketpilot.core.enums import AssetType, Interval
from marketpilot.core.exceptions import ExchangeAPIError, ExchangeConnectionError
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.models.market import Kline, Ticker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def exchange_settings() -> ExchangeSettings:
    """Minimal exchange settings for testing."""
    return ExchangeSettings(testnet=True)


@pytest.fixture()
def mock_pybit() -> MagicMock:
    """A mocked ``pybit.unified_trading.HTTP`` instance."""
    mock = MagicMock()

    # get_server_time
    mock.get_server_time.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "timeSecond": "1719849600",
            "timeNano": "1719849600123456789",
        },
    }

    # get_tickers
    mock.get_tickers.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "67500.50",
                    "bid1Price": "67500.00",
                    "ask1Price": "67501.00",
                    "highPrice24h": "68000.00",
                    "lowPrice24h": "66000.00",
                    "volume24h": "12345.67",
                    "turnover24h": "823456789.00",
                },
            ],
        },
    }

    # get_kline
    mock.get_kline.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "symbol": "BTCUSDT",
            "list": [
                # [startTime, open, high, low, close, volume, turnover]
                ["1719849600000", "67000.0", "67500.0", "66800.0", "67200.0", "100.5", "6730000.0"],
                ["1719846000000", "66500.0", "67100.0", "66400.0", "67000.0", "200.3", "13400000.0"],
            ],
        },
    }

    # get_instruments_info
    mock.get_instruments_info.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "baseCoin": "BTC",
                    "quoteCoin": "USDT",
                    "contractType": "LinearPerpetual",
                    "settleCoin": "USDT",
                    "status": "Trading",
                    "lotSizeFilter": {
                        "minOrderQty": "0.001",
                        "maxOrderQty": "100",
                        "qtyStep": "0.001",
                        "postOnlyMaxOrderQty": "1000.0"
                    },
                    "priceFilter": {
                        "minPrice": "0.1",
                        "maxPrice": "100000.0",
                        "tickSize": "0.10"
                    },
                    "leverageFilter": {
                        "minLeverage": "1",
                        "maxLeverage": "100",
                        "leverageStep": "0.01"
                    }
                }
            ],
        },
    }

    return mock


@pytest.fixture()
def client(exchange_settings: ExchangeSettings, mock_pybit: MagicMock) -> BybitClient:
    """A BybitClient with an injected mock HTTP session."""
    c = BybitClient(exchange_settings=exchange_settings, execution_mode=ExecutionMode.PAPER)
    c._http = mock_pybit  # inject mock
    return c


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

class TestConnect:
    """Tests for connect / disconnect lifecycle."""

    async def test_connect_success(self, exchange_settings: ExchangeSettings, mock_pybit: MagicMock) -> None:
        client = BybitClient(exchange_settings=exchange_settings, execution_mode=ExecutionMode.PAPER)
        with patch("marketpilot.exchange.bybit_client.PybitHTTP", return_value=mock_pybit):
            await client.connect()
        assert client._http is mock_pybit

    async def test_connect_failure_raises(self, exchange_settings: ExchangeSettings) -> None:
        client = BybitClient(exchange_settings=exchange_settings, execution_mode=ExecutionMode.PAPER)
        with patch("marketpilot.exchange.bybit_client.PybitHTTP", side_effect=Exception("network error")):
            with pytest.raises(ExchangeConnectionError, match="Failed to connect"):
                await client.connect()

    async def test_disconnect(self, client: BybitClient) -> None:
        await client.disconnect()
        assert client._http is None


# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

class TestPing:
    """Tests for the ping command."""

    async def test_ping_returns_dict(self, client: BybitClient) -> None:
        result = await client.ping()

        assert result["connected"] is True
        assert result["environment"] == "MAINNET"
        assert "server_time" in result
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], float)

    async def test_ping_not_connected_raises(self, exchange_settings: ExchangeSettings) -> None:
        client = BybitClient(exchange_settings=exchange_settings, execution_mode=ExecutionMode.PAPER)
        with pytest.raises(ExchangeConnectionError, match="not connected"):
            await client.ping()


# ---------------------------------------------------------------------------
# Server Time
# ---------------------------------------------------------------------------

class TestGetServerTime:
    """Tests for get_server_time."""

    async def test_returns_datetime(self, client: BybitClient) -> None:
        result = await client.get_server_time()

        assert isinstance(result, datetime)
        assert result.tzinfo == UTC


# ---------------------------------------------------------------------------
# Tickers
# ---------------------------------------------------------------------------

class TestGetTickers:
    """Tests for get_tickers."""

    async def test_single_ticker(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        tickers = await client.get_tickers("BTCUSDT", AssetType.LINEAR)

        assert len(tickers) == 1
        t = tickers[0]
        assert isinstance(t, Ticker)
        assert t.symbol == "BTCUSDT"
        assert t.asset_type == AssetType.LINEAR
        assert t.last_price == "67500.50"
        assert t.bid_price == "67500.00"

        # Verify pybit was called with correct params
        mock_pybit.get_tickers.assert_called_once_with(
            category="linear", symbol="BTCUSDT",
        )

    async def test_empty_symbol_gets_all(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        await client.get_tickers("", AssetType.SPOT)
        mock_pybit.get_tickers.assert_called_once_with(category="spot")


# ---------------------------------------------------------------------------
# Klines
# ---------------------------------------------------------------------------

class TestGetKlines:
    """Tests for get_klines."""

    async def test_returns_kline_list(self, client: BybitClient) -> None:
        klines = await client.get_klines("BTCUSDT", Interval.H1, limit=2, asset_type=AssetType.LINEAR)

        assert len(klines) == 2
        k = klines[0]
        assert isinstance(k, Kline)
        assert k.symbol == "BTCUSDT"
        assert k.interval == Interval.H1
        assert k.open == "67000.0"
        assert k.close == "67200.0"
        assert isinstance(k.open_time, datetime)

    async def test_kline_params(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        await client.get_klines("ETHUSDT", Interval.M15, limit=100, asset_type=AssetType.LINEAR)

        mock_pybit.get_kline.assert_called_once_with(
            category="linear",
            symbol="ETHUSDT",
            interval="15",
            limit=100,
        )


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

class TestGetInstruments:
    """Tests for get_instruments."""

    async def test_returns_instrument_list(self, client: BybitClient) -> None:
        instruments = await client.get_instruments(AssetType.LINEAR)

        assert len(instruments) == 1
        inst = instruments[0]
        assert isinstance(inst, InstrumentInfo)
        assert inst.symbol == "BTCUSDT"
        assert inst.base_coin == "BTC"
        assert inst.quote_coin == "USDT"
        assert inst.tick_size == "0.10"
        assert inst.min_order_qty == "0.001"
        assert inst.max_leverage == "100"

    async def test_instrument_with_symbol(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        await client.get_instruments(AssetType.LINEAR, symbol="BTCUSDT")

        mock_pybit.get_instruments_info.assert_called_once_with(
            category="linear", symbol="BTCUSDT",
        )

    async def test_instrument_pagination(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        # Mock a 2-page response
        mock_pybit.get_instruments_info.side_effect = [
            {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "category": "linear",
                    "list": [{"symbol": "BTCUSDT", "contractType": "LinearPerpetual", "settleCoin": "USDT", "status": "Trading"}],
                    "nextPageCursor": "page2",
                },
            },
            {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "category": "linear",
                    "list": [{"symbol": "ETHUSDT", "contractType": "LinearPerpetual", "settleCoin": "USDT", "status": "Trading"}],
                    "nextPageCursor": "",
                },
            },
        ]
        
        instruments = await client.get_instruments(AssetType.LINEAR)
        assert len(instruments) == 2
        assert instruments[0].symbol == "BTCUSDT"
        assert instruments[1].symbol == "ETHUSDT"
        
        assert mock_pybit.get_instruments_info.call_count == 2
        mock_pybit.get_instruments_info.assert_any_call(category="linear")
        mock_pybit.get_instruments_info.assert_any_call(category="linear", cursor="page2")


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Tests for API error handling."""

    async def test_non_zero_retcode_raises(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        mock_pybit.get_server_time.return_value = {
            "retCode": 10001,
            "retMsg": "Invalid API key",
            "result": {},
        }

        with pytest.raises(ExchangeAPIError, match="Invalid API key"):
            await client.get_server_time()

    async def test_api_error_includes_code(self, client: BybitClient, mock_pybit: MagicMock) -> None:
        mock_pybit.get_tickers.return_value = {
            "retCode": 10002,
            "retMsg": "Request parameter error",
            "result": {},
        }

        with pytest.raises(ExchangeAPIError) as exc_info:
            await client.get_tickers("INVALID", AssetType.LINEAR)

        assert exc_info.value.ret_code == 10002
