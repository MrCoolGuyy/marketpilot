"""
MarketPilot Exchange â€” Bybit V5 Unified Trading API client.

Wraps the synchronous ``pybit.unified_trading.HTTP`` class in an async
interface.  All blocking I/O is offloaded to a thread-pool via
``asyncio.to_thread`` so the event loop stays responsive.

The client reads credentials from ``AppSettings.exchange`` and
automatically selects testnet vs mainnet endpoints.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from pybit.unified_trading import HTTP as PybitHTTP

from marketpilot.config.settings import AppSettings, ExchangeSettings
from marketpilot.core.enums import MarketDataEnvironment, ExecutionMode
from marketpilot.core.constants import DEFAULT_RECV_WINDOW
from marketpilot.core.enums import AssetType, Interval
from marketpilot.core.exceptions import ExchangeAPIError, ExchangeConnectionError
from marketpilot.models.instrument import InstrumentInfo
from marketpilot.models.market import Kline, Ticker
from marketpilot.utils.decorators import log_execution, retry
from marketpilot.utils.helpers import ms_to_datetime


class BybitClient:
    """Async Bybit V5 exchange client.

    Usage::

        client = BybitClient(settings)
        await client.connect()

        ticker = await client.get_tickers("BTCUSDT", AssetType.LINEAR)
        server_time = await client.get_server_time()

        await client.disconnect()

    Parameters
    ----------
    settings:
        Exchange settings containing API credentials and tuning knobs.
    """

    def __init__(self, exchange_settings: ExchangeSettings, execution_mode: ExecutionMode) -> None:
        self._execution_mode = execution_mode
        self._demo_flag = (self._execution_mode == ExecutionMode.DEMO)
        self._settings = exchange_settings
        self._environment = exchange_settings.environment

        self._http: PybitHTTP | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialise the pybit HTTP session.

        Validates connectivity by fetching the server time.
        """
        try:
            api_key = self._settings.api_key.get_secret_value() or None
            api_secret = self._settings.api_secret.get_secret_value() or None

            is_testnet = (self._environment == MarketDataEnvironment.TESTNET)

            self._http = PybitHTTP(
                testnet=is_testnet,
                demo=self._demo_flag,
                api_key=api_key,
                api_secret=api_secret,
                recv_window=DEFAULT_RECV_WINDOW,
                timeout=getattr(self._settings, "timeout", 5),
                max_retries=getattr(self._settings, "max_retries", 3),
                retry_delay=getattr(self._settings, "retry_backoff", 1.0),
                force_retry=True,
                log_requests=False,
            )

            # Validate connectivity
            result = await self._call(self._http.get_server_time)
            env_str = self._environment.value
            logger.info(
                "Connected to Bybit {} (server_time={})",
                env_str,
                result.get("result", {}).get("timeSecond", "?"),
            )
        except Exception as exc:
            raise ExchangeConnectionError(
                f"Failed to connect to Bybit: {exc}"
            ) from exc

    async def disconnect(self) -> None:
        """Release the HTTP session."""
        self._http = None
        logger.info("Bybit client disconnected")

    # ------------------------------------------------------------------
    # Public Market Data
    # ------------------------------------------------------------------

    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def ping(self) -> dict[str, Any]:
        """Lightweight connectivity check.

        Returns a dict with ``connected``, ``server_time``,
        ``latency_ms``, and ``environment``.
        """
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")
        start = time.perf_counter()
        result = await self._call(self._http.get_server_time)
        latency_ms = (time.perf_counter() - start) * 1_000

        time_nano = result.get("result", {}).get("timeNano", "0")
        time_second = result.get("result", {}).get("timeSecond", "0")

        return {
            "connected": True,
            "server_time": time_second,
            "server_time_nano": time_nano,
            "latency_ms": round(latency_ms, 2),
            "environment": self._environment.value,
        }

    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def get_server_time(self) -> datetime:
        """Fetch the exchange server time as a UTC ``datetime``."""
        result = await self._call(self._http.get_server_time)
        time_nano = int(result["result"]["timeNano"])
        # timeNano is in nanoseconds â†’ convert to seconds
        return datetime.fromtimestamp(time_nano / 1_000_000_000, tz=UTC)

    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def get_tickers(
        self,
        symbol: str,
        asset_type: AssetType,
    ) -> list[Ticker]:
        """Fetch ticker(s) for a symbol or all symbols in a category.

        Parameters
        ----------
        symbol:
            Trading pair (e.g. ``"BTCUSDT"``).  Pass ``""`` for all.
        asset_type:
            Product category.
        """
        params: dict[str, Any] = {"category": str(asset_type)}
        if symbol:
            params["symbol"] = symbol

        result = await self._call(self._http_session.get_tickers, **params)
        raw_list = result.get("result", {}).get("list", [])

        tickers: list[Ticker] = []
        time_server = int(result.get("time", time.time() * 1000))
        now = ms_to_datetime(time_server)

        for item in raw_list:
            tickers.append(
                Ticker(
                    symbol=item["symbol"],
                    asset_type=asset_type,
                    last_price=item.get("lastPrice", "0"),
                    bid_price=item.get("bid1Price", "0"),
                    ask_price=item.get("ask1Price", "0"),
                    high_24h=item.get("highPrice24h", "0"),
                    low_24h=item.get("lowPrice24h", "0"),
                    price_change_percent_24h=item.get("price24hPcnt", "0"),
                    volume_24h=item.get("volume24h", "0"),
                    turnover_24h=item.get("turnover24h", "0"),
                    timestamp=now,
                )
            )
        return tickers

    @log_execution
    @retry(max_retries=3, backoff_base=1.0)
    async def get_klines(
        self,
        symbol: str,
        interval: Interval,
        limit: int = 200,
        asset_type: AssetType = AssetType.LINEAR,
    ) -> list[Kline]:
        """Fetch historical kline / candlestick data."""
        result = await self._call(
            self._http_session.get_kline,
            category=str(asset_type),
            symbol=symbol,
            interval=str(interval),
            limit=limit,
        )
        raw_list = result.get("result", {}).get("list", [])

        klines: list[Kline] = []
        for item in raw_list:
            # Bybit returns: [startTime, open, high, low, close, volume, turnover]
            klines.append(
                Kline(
                    symbol=symbol,
                    interval=interval,
                    open_time=ms_to_datetime(int(item[0])),
                    open=item[1],
                    high=item[2],
                    low=item[3],
                    close=item[4],
                    volume=item[5],
                    turnover=item[6],
                )
            )
        return klines

    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def get_instruments(
        self,
        asset_type: AssetType,
        *,
        symbol: str = "",
    ) -> list[InstrumentInfo]:
        """Fetch instrument specifications.

        Parameters
        ----------
        asset_type:
            Product category.
        symbol:
            Optional specific symbol to query.
        """
        params: dict[str, Any] = {"category": str(asset_type)}
        if symbol:
            params["symbol"] = symbol

        instruments: list[InstrumentInfo] = []

        while True:
            result = await self._call(
                self._http_session.get_instruments_info,
                **params,
            )
            data = result.get("result", {})
            raw_list = data.get("list", [])

            for item in raw_list:
                # strictly enforce MarketPilot v1 universe
                if asset_type == AssetType.LINEAR:
                    if item.get("contractType") != "LinearPerpetual":
                        continue
                    if item.get("settleCoin") != "USDT":
                        continue
                    if item.get("status") != "Trading":
                        continue

                lot_filter = item.get("lotSizeFilter", {})
                price_filter = item.get("priceFilter", {})
                leverage_filter = item.get("leverageFilter", {})

                instruments.append(
                    InstrumentInfo(
                        symbol=item["symbol"],
                        asset_type=asset_type,
                        base_coin=item.get("baseCoin", ""),
                        quote_coin=item.get("quoteCoin", ""),
                        status=item.get("status", ""),
                        tick_size=price_filter.get("tickSize", "0"),
                        min_order_qty=lot_filter.get("minOrderQty", "0"),
                        max_order_qty=lot_filter.get("maxOrderQty", "0"),
                        qty_step=lot_filter.get("qtyStep", "0"),
                        min_leverage=leverage_filter.get("minLeverage", "1"),
                        max_leverage=leverage_filter.get("maxLeverage", "1"),
                    )
                )

            next_cursor = data.get("nextPageCursor")
            if not next_cursor or symbol:
                break

            params["cursor"] = next_cursor

        return instruments



    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _http_session(self) -> PybitHTTP:
        """Return the active pybit HTTP session or raise."""
        if self._http is None:
            raise ExchangeConnectionError(
                "Client not connected â€” call connect() first"
            )
        return self._http

    async def _call(self, method: Any, **kwargs: Any) -> dict[str, Any]:
        """Run a synchronous pybit method in a thread pool.

        Validates the response ``retCode`` and raises ``ExchangeAPIError``
        on non-zero codes.
        """
        result: dict[str, Any] = await asyncio.to_thread(method, **kwargs)

        ret_code = result.get("retCode", -1)
        if ret_code != 0:
            ret_msg = result.get("retMsg", "Unknown error")
            logger.error(
                "Bybit API error: retCode={}, retMsg={}, method={}",
                ret_code,
                ret_msg,
                getattr(method, "__name__", str(method)),
            )
            raise ExchangeAPIError(
                status_code=ret_code,
                message=ret_msg,
                ret_code=ret_code,
            )

        return result

    # ------------------------------------------------------------------
    # Execution (Demo Only)
    # ------------------------------------------------------------------

    @retry(max_retries=0)  # We do NOT want to auto-retry order placement to prevent duplicates
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str | None = None,
        time_in_force: str = "GTC",
        order_link_id: str | None = None,
        category: str = "linear",
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """Place an order safely.

        Raises RuntimeError immediately if attempting to execute on MAINNET.
        """
        if self._execution_mode != ExecutionMode.DEMO:
            logger.error("ATTEMPTED TO PLACE ORDER ON NON-DEMO PROFILE. ABORTING.")
            raise RuntimeError("CRITICAL: Mainnet/Testnet execution is strictly disabled. Use Demo only.")

        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        logger.info(f"[{self._execution_mode.value}] Placing {side} {order_type} order for {qty} {symbol}")

        kwargs = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "timeInForce": time_in_force,
            "reduceOnly": reduce_only,
        }
        if price:
            kwargs["price"] = price
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id

        return await self._call(self._http.place_order, **kwargs)

    @retry(max_retries=3, backoff_base=1.0)
    async def get_order_status(self, symbol: str, order_link_id: str, category: str = "linear") -> dict[str, Any]:
        """Query order status using orderLinkId."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        kwargs = {
            "category": category,
            "symbol": symbol,
            "orderLinkId": order_link_id
        }
        return await self._call(self._http.get_open_orders, **kwargs)

    @retry(max_retries=3, backoff_base=1.0)
    async def set_trading_stop(
        self,
        symbol: str,
        position_idx: int,
        take_profit: str | None = None,
        stop_loss: str | None = None,
        category: str = "linear",
    ) -> dict[str, Any]:
        """Set stop loss and take profit for a position."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        kwargs = {
            "category": category,
            "symbol": symbol,
            "positionIdx": position_idx,
        }
        if take_profit:
            kwargs["takeProfit"] = take_profit
        if stop_loss:
            kwargs["stopLoss"] = stop_loss

        return await self._call(self._http.set_trading_stop, **kwargs)

    @retry(max_retries=3, backoff_base=1.0)
    async def get_positions(self, symbol: str | None = None, category: str = "linear") -> dict[str, Any]:
        """Fetch current positions."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        kwargs = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol

        return await self._call(self._http.get_positions, **kwargs)

    @retry(max_retries=3, backoff_base=1.0)
    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict[str, Any]:
        """Fetch wallet balance."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        return await self._call(self._http.get_wallet_balance, accountType=account_type)


    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def get_active_orders(self, category: str = "linear", settle_coin: str = "USDT") -> list[dict]:
        """Fetch all active regular and conditional orders."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        orders = {}
        cursor = ""
        while True:
            params = {"category": category, "settleCoin": settle_coin}
            if cursor:
                params["cursor"] = cursor

            res = await self._call(self._http.get_open_orders, **params)
            data = res.get("result", {})
            for o in data.get("list", []):
                oid = o.get("orderId")
                if oid:
                    orders[oid] = o

            cursor = data.get("nextPageCursor")
            if not cursor:
                break
        return list(orders.values())

    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def get_order_history(self, category: str = "linear", settle_coin: str = "USDT", limit: int = 50, cursor: str = "") -> dict[str, Any]:
        """Fetch a page of recent order history."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        params = {"category": category, "settleCoin": settle_coin, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        res = await self._call(self._http.get_order_history, **params)
        return res.get("result", {})

    @log_execution
    @retry(max_retries=3, exceptions=(ExchangeAPIError, OSError))
    async def get_execution_history(self, category: str = "linear", settle_coin: str = "USDT", limit: int = 50, cursor: str = "") -> dict[str, Any]:
        """Fetch a page of recent execution/fill history."""
        if not self._http:
            raise ExchangeConnectionError("Client is not connected")

        params = {"category": category, "settleCoin": settle_coin, "limit": limit}
        if cursor:
            params["cursor"] = cursor

        res = await self._call(self._http.get_executions, **params)
        return res.get("result", {})
