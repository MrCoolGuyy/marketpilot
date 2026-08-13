"""
MarketPilot Tests — Scanner unit tests.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from marketpilot.config.settings import ScannerSettings
from marketpilot.core.enums import AssetType
from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.models.market import Ticker
from marketpilot.scanner.service import ScannerService
from datetime import datetime, UTC

@pytest.fixture
def mock_settings() -> ScannerSettings:
    return ScannerSettings(
        asset_type="linear",
        quote_coin="USDT",
        min_turnover_24h=1000.0,
        max_results=2,
    )


@pytest.fixture
def mock_client() -> AsyncMock:
    client = MagicMock(spec=BybitClient)
    client.get_instruments = AsyncMock()
    client.get_tickers = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_scanner_filters_inactive_and_non_quote(mock_client: AsyncMock, mock_settings: ScannerSettings) -> None:
    scanner = ScannerService(mock_client, mock_settings)

    mock_client.get_instruments.return_value = [
        InstrumentInfo(symbol="BTCUSDT", asset_type=AssetType.LINEAR, base_coin="BTC", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
        InstrumentInfo(symbol="ETHUSDT", asset_type=AssetType.LINEAR, base_coin="ETH", quote_coin="USDT", status="Settling", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
        InstrumentInfo(symbol="BTCUSDC", asset_type=AssetType.LINEAR, base_coin="BTC", quote_coin="USDC", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
    ]

    now = datetime.now(tz=UTC)
    mock_client.get_tickers.return_value = [
        Ticker(symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="50000", bid_price="50000", ask_price="50001", high_24h="51000", low_24h="49000", price_change_percent_24h="0.01", volume_24h="10", turnover_24h="500000", timestamp=now),
        Ticker(symbol="ETHUSDT", asset_type=AssetType.LINEAR, last_price="3000", bid_price="3000", ask_price="3001", high_24h="3100", low_24h="2900", price_change_percent_24h="0.02", volume_24h="10", turnover_24h="30000", timestamp=now),
        Ticker(symbol="BTCUSDC", asset_type=AssetType.LINEAR, last_price="50000", bid_price="50000", ask_price="50001", high_24h="51000", low_24h="49000", price_change_percent_24h="0.01", volume_24h="10", turnover_24h="500000", timestamp=now),
    ]

    results = await scanner.scan()
    assert len(results) == 1
    assert results[0].symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_scanner_filters_turnover(mock_client: AsyncMock, mock_settings: ScannerSettings) -> None:
    scanner = ScannerService(mock_client, mock_settings)

    mock_client.get_instruments.return_value = [
        InstrumentInfo(symbol="BTCUSDT", asset_type=AssetType.LINEAR, base_coin="BTC", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
        InstrumentInfo(symbol="LTCUSDT", asset_type=AssetType.LINEAR, base_coin="LTC", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
    ]

    now = datetime.now(tz=UTC)
    mock_client.get_tickers.return_value = [
        Ticker(symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="50000", bid_price="50000", ask_price="50001", high_24h="51000", low_24h="49000", price_change_percent_24h="0.01", volume_24h="10", turnover_24h="5000", timestamp=now), # > 1000
        Ticker(symbol="LTCUSDT", asset_type=AssetType.LINEAR, last_price="50", bid_price="50", ask_price="51", high_24h="55", low_24h="45", price_change_percent_24h="0.01", volume_24h="10", turnover_24h="999", timestamp=now), # < 1000
    ]

    results = await scanner.scan()
    assert len(results) == 1
    assert results[0].symbol == "BTCUSDT"


@pytest.mark.asyncio
async def test_scanner_handles_malformed_ticker(mock_client: AsyncMock, mock_settings: ScannerSettings) -> None:
    scanner = ScannerService(mock_client, mock_settings)

    mock_client.get_instruments.return_value = [
        InstrumentInfo(symbol="BTCUSDT", asset_type=AssetType.LINEAR, base_coin="BTC", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
        InstrumentInfo(symbol="ETHUSDT", asset_type=AssetType.LINEAR, base_coin="ETH", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
    ]

    now = datetime.now(tz=UTC)
    mock_client.get_tickers.return_value = [
        Ticker(symbol="BTCUSDT", asset_type=AssetType.LINEAR, last_price="50000", bid_price="50000", ask_price="50001", high_24h="51000", low_24h="49000", price_change_percent_24h="0.01", volume_24h="10", turnover_24h="invalid", timestamp=now),
        Ticker(symbol="ETHUSDT", asset_type=AssetType.LINEAR, last_price="3000", bid_price="3000", ask_price="3001", high_24h="3100", low_24h="2900", price_change_percent_24h="0.02", volume_24h="10", turnover_24h="30000", timestamp=now),
    ]

    results = await scanner.scan()
    assert len(results) == 1
    assert results[0].symbol == "ETHUSDT"


@pytest.mark.asyncio
async def test_scanner_ranks_and_limits(mock_client: AsyncMock, mock_settings: ScannerSettings) -> None:
    scanner = ScannerService(mock_client, mock_settings)

    mock_client.get_instruments.return_value = [
        InstrumentInfo(symbol="A", asset_type=AssetType.LINEAR, base_coin="A", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
        InstrumentInfo(symbol="B", asset_type=AssetType.LINEAR, base_coin="B", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
        InstrumentInfo(symbol="C", asset_type=AssetType.LINEAR, base_coin="C", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
    ]

    now = datetime.now(tz=UTC)
    mock_client.get_tickers.return_value = [
        Ticker(symbol="A", asset_type=AssetType.LINEAR, last_price="1", bid_price="1", ask_price="1", high_24h="1", low_24h="1", price_change_percent_24h="0", volume_24h="1", turnover_24h="5000", timestamp=now),
        Ticker(symbol="B", asset_type=AssetType.LINEAR, last_price="1", bid_price="1", ask_price="1", high_24h="1", low_24h="1", price_change_percent_24h="0", volume_24h="1", turnover_24h="10000", timestamp=now),
        Ticker(symbol="C", asset_type=AssetType.LINEAR, last_price="1", bid_price="1", ask_price="1", high_24h="1", low_24h="1", price_change_percent_24h="0", volume_24h="1", turnover_24h="8000", timestamp=now),
    ]

    results = await scanner.scan()
    # Limit is 2 in mock_settings. Expected order: B (10000), C (8000)
    assert len(results) == 2
    assert results[0].symbol == "B"
    assert results[1].symbol == "C"


@pytest.mark.asyncio
async def test_scanner_no_results(mock_client: AsyncMock, mock_settings: ScannerSettings) -> None:
    scanner = ScannerService(mock_client, mock_settings)

    mock_client.get_instruments.return_value = []
    mock_client.get_tickers.return_value = []

    results = await scanner.scan()
    assert results == []

@pytest.mark.asyncio
async def test_scanner_upstream_failure(mock_client: AsyncMock, mock_settings: ScannerSettings) -> None:
    scanner = ScannerService(mock_client, mock_settings)

    mock_client.get_instruments.return_value = [
        InstrumentInfo(symbol="BTCUSDT", asset_type=AssetType.LINEAR, base_coin="BTC", quote_coin="USDT", status="Trading", tick_size="0.1", min_order_qty="0.001", max_order_qty="100", qty_step="0.001", min_leverage="1", max_leverage="100"),
    ]
    
    # Simulate an upstream exception from the client
    mock_client.get_tickers.side_effect = Exception("Upstream API error")

    with pytest.raises(Exception, match="Upstream API error"):
        await scanner.scan()
