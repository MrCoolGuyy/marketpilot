"""
MarketPilot Exchange - Market Data Fetcher.

Responsible purely for fetching raw data from the exchange and 
packaging it into a RawMarketData model. It does not perform any 
feature engineering or technical analysis.
"""

from __future__ import annotations

import asyncio
import time
from typing import Sequence
from decimal import Decimal

from loguru import logger

from marketpilot.exchange.bybit_client import BybitClient
from marketpilot.models.market_data import RawMarketData
from marketpilot.core.enums import AssetType, Interval


class MarketDataFetcher:
    """Infrastructure layer for retrieving raw market data."""

    def __init__(self, client: BybitClient) -> None:
        self._client = client

    async def fetch(
        self, 
        symbol: str, 
        asset_type: AssetType = AssetType.LINEAR,
        interval: Interval = Interval.H1,
        kline_limit: int = 100
    ) -> RawMarketData:
        """Fetch raw market data for a single instrument."""
        
        # Concurrently fetch tickers and klines
        tickers_task = self._client.get_tickers(symbol=symbol, asset_type=asset_type)
        klines_task = self._client.get_klines(symbol=symbol, interval=interval, limit=kline_limit, asset_type=asset_type)
        
        tickers, klines = await asyncio.gather(tickers_task, klines_task)
        
        if not tickers:
            raise ValueError(f"No ticker found for {symbol}")
            
        ticker = tickers[0]
        
        return RawMarketData(
            symbol=symbol,
            asset_type=asset_type,
            ticker=ticker,
            klines=klines,
            timestamp=time.time()
        )

    async def fetch_scan_candidates(
        self,
        quote_coin: str,
        min_turnover_24h: float,
        limit: int,
        asset_type: AssetType = AssetType.LINEAR,
        interval: Interval = Interval.H1,
        kline_limit: int = 100
    ) -> list[RawMarketData]:
        """
        Fetch top trading candidates matching the criteria, complete with raw klines.
        This optimizes API calls by fetching all tickers once, filtering, 
        and only fetching klines for the top N candidates.
        """
        # 1. Fetch instruments to filter by quote coin and active status
        instruments = await self._client.get_instruments(asset_type)
        active_symbols = {
            inst.symbol
            for inst in instruments
            if inst.quote_coin == quote_coin and inst.status == "Trading"
        }
        
        # 2. Fetch all tickers in one call
        all_tickers = await self._client.get_tickers(symbol="", asset_type=asset_type)
        
        # 3. Filter and sort tickers
        min_turnover = Decimal(str(min_turnover_24h))
        valid_tickers = []
        for t in all_tickers:
            if t.symbol not in active_symbols:
                continue
            try:
                turnover = Decimal(t.turnover_24h)
                if turnover >= min_turnover:
                    valid_tickers.append((t, turnover))
            except Exception:
                pass
                
        # Sort by turnover desc and take top N
        valid_tickers.sort(key=lambda x: x[1], reverse=True)
        top_tickers = [t[0] for t in valid_tickers[:limit]]
        
        # 4. Fetch klines for the top candidates concurrently
        # Limit to 10 concurrent requests to prevent connection pool churn
        sem = asyncio.Semaphore(10)
        
        async def _fetch_full_data(ticker) -> RawMarketData | None:
            async with sem:
                try:
                    klines = await self._client.get_klines(
                        symbol=ticker.symbol, 
                        interval=interval, 
                        limit=kline_limit, 
                        asset_type=asset_type
                    )
                    return RawMarketData(
                        symbol=ticker.symbol,
                        asset_type=asset_type,
                        ticker=ticker,
                        klines=klines,
                        timestamp=time.time()
                    )
                except Exception as e:
                    logger.warning("Failed to fetch klines for {}: {}", ticker.symbol, e)
                    return None
                
        tasks = [_fetch_full_data(t) for t in top_tickers]
        results = await asyncio.gather(*tasks)
        
        return [r for r in results if r is not None]

