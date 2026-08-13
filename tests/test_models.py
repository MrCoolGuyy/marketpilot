"""
Tests for Pydantic domain models.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from marketpilot.core.enums import AssetType, Interval, OrderSide, OrderType, TimeInForce
from marketpilot.models.account import Balance, WalletInfo
from marketpilot.models.market import Kline, OrderBook, OrderBookEntry, Ticker
from marketpilot.models.order import OrderRequest, OrderResponse, Position


NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


class TestTicker:
    """Ticker model validation."""

    def test_valid_ticker(self) -> None:
        t = Ticker(
            symbol="BTCUSDT",
            asset_type=AssetType.LINEAR,
            last_price="67000.50",
            bid_price="67000.00",
            ask_price="67001.00",
            high_24h="68000.00",
            low_24h="66000.00",
            price_change_percent_24h="0.01",
            volume_24h="12345.67",
            turnover_24h="823456789.00",
            timestamp=NOW,
        )
        assert t.symbol == "BTCUSDT"
        assert t.asset_type == AssetType.LINEAR

    def test_ticker_is_frozen(self) -> None:
        t = Ticker(
            symbol="BTCUSDT",
            asset_type=AssetType.SPOT,
            last_price="1",
            bid_price="1",
            ask_price="1",
            high_24h="1",
            low_24h="1",
            price_change_percent_24h="0",
            volume_24h="1",
            turnover_24h="1",
            timestamp=NOW,
        )
        with pytest.raises(ValidationError):
            t.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Ticker(symbol="BTCUSDT", asset_type=AssetType.SPOT, timestamp=NOW)  # type: ignore[call-arg]


class TestKline:
    """Kline model validation."""

    def test_valid_kline(self) -> None:
        k = Kline(
            symbol="ETHUSDT",
            interval=Interval.H1,
            open_time=NOW,
            open="3500.00",
            high="3550.00",
            low="3480.00",
            close="3520.00",
            volume="1000.00",
            turnover="3510000.00",
        )
        assert k.interval == Interval.H1
        assert k.close == "3520.00"


class TestOrderBook:
    """OrderBook model validation."""

    def test_empty_book(self) -> None:
        ob = OrderBook(
            symbol="BTCUSDT",
            asset_type=AssetType.SPOT,
            timestamp=NOW,
        )
        assert ob.bids == []
        assert ob.asks == []

    def test_with_entries(self) -> None:
        ob = OrderBook(
            symbol="BTCUSDT",
            asset_type=AssetType.LINEAR,
            bids=[OrderBookEntry(price="67000.0", quantity="1.5")],
            asks=[OrderBookEntry(price="67001.0", quantity="0.8")],
            timestamp=NOW,
        )
        assert len(ob.bids) == 1
        assert ob.asks[0].price == "67001.0"


class TestOrderRequest:
    """OrderRequest model validation."""

    def test_market_order(self) -> None:
        req = OrderRequest(
            symbol="BTCUSDT",
            asset_type=AssetType.LINEAR,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            qty="0.01",
        )
        assert req.price is None
        assert req.time_in_force == TimeInForce.GTC

    def test_limit_order(self) -> None:
        req = OrderRequest(
            symbol="ETHUSDT",
            asset_type=AssetType.SPOT,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            qty="1.0",
            price="3500.00",
        )
        assert req.price == "3500.00"


class TestBalance:
    """Balance model validation."""

    def test_valid_balance(self) -> None:
        b = Balance(
            coin="USDT",
            wallet_balance="10000.00",
            available_balance="9500.00",
            updated_at=NOW,
        )
        assert b.coin == "USDT"
        assert b.locked == "0"  # default


class TestWalletInfo:
    """WalletInfo model validation."""

    def test_empty_wallet(self) -> None:
        w = WalletInfo(
            account_type="UNIFIED",
            total_equity="10000",
            total_wallet_balance="10000",
            total_available_balance="9500",
            updated_at=NOW,
        )
        assert w.balances == []
