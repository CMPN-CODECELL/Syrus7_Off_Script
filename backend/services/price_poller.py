"""Publish market quotes from the configured data feed to Redis."""
import asyncio
import json
from datetime import timedelta
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis

from config import settings
from services.instruments import INSTRUMENTS
from services.stock_data_service import get_stock_provider

SYMBOL_ALIAS = {"^NSEI": "NIFTY50"}
POLL_INTERVAL = 60
MARKET_SYMBOLS = [*INSTRUMENTS, "^NSEI", "^BSESN"]
INDEX_ALIAS = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX"}


class PricePoller:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._running = False
        self.first_snapshot = asyncio.Event()

    async def start(self):
        """Refresh the mock quote cache until the application shuts down."""
        self._running = True
        print(f"{settings.market_data_provider} quote poller: starting first fetch...")
        while self._running:
            try:
                await self._fetch_and_cache()
            except Exception as error:
                print(f"Demo quote poller error: {error}")
            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        self._running = False

    async def _fetch_and_cache(self):
        """Fetch configured quotes without substituting demo values."""
        if settings.market_data_provider.lower() == "yahoo":
            provider = get_stock_provider("yahoo")
            results = await asyncio.gather(*(self._get_provider_quote(provider, symbol) for symbol in MARKET_SYMBOLS))
            prices = {symbol: price for symbol, price in results if price is not None}
            source = "yahoo_finance"
        elif settings.market_data_provider.lower() == "demo":
            async with httpx.AsyncClient(timeout=5.0) as http:
                results = await asyncio.gather(*(self._get_demo_quote(http, symbol) for symbol in INSTRUMENTS))
            prices = {symbol: price for symbol, price in results if price is not None}
            source = "fixed_demo_fallback"
        else:
            raise ValueError("MARKET_DATA_PROVIDER must be 'demo' or 'yahoo'.")

        if not prices:
            print(f"{settings.market_data_provider} quote feed returned no prices")
            return

        snapshot = {}
        sources = {}
        pipe = self.redis.pipeline()
        for symbol, price in prices.items():
            redis_key = INDEX_ALIAS.get(symbol, SYMBOL_ALIAS.get(symbol, symbol))
            pipe.set(f"price:{redis_key}", str(price), ex=180)
            snapshot[redis_key] = price
            sources[redis_key] = source
            point = json.dumps({"time": datetime.now(timezone.utc).isoformat(), "price": price})
            history_key = f"market:history:{redis_key}"
            pipe.rpush(history_key, point)
            pipe.ltrim(history_key, -2500, -1)
            pipe.expire(history_key, int(timedelta(days=7).total_seconds()))

        pipe.set(
            "price:snapshot",
            json.dumps({
                "prices": snapshot,
                "sources": sources,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "provider": source,
                "mode": "external_market_data" if source == "yahoo_finance" else "demo",
            }),
            ex=180,
        )

        await pipe.execute()
        self.first_snapshot.set()
        print(f"{source} quotes updated: {', '.join(f'{symbol}={price}' for symbol, price in snapshot.items())}")

    @staticmethod
    async def _get_provider_quote(provider, symbol: str):
        try:
            quote = await provider.get_quote(symbol)
            price = float(quote.get("ltp") or 0)
            return (symbol, round(price, 2)) if price > 0 else (symbol, None)
        except Exception as error:
            print(f"Market quote unavailable for {symbol}: {error}")
            return symbol, None

    @staticmethod
    async def _get_demo_quote(http: httpx.AsyncClient, symbol: str):
        try:
            response = await http.get(
                f"{settings.mock_api_url}/quote/{symbol}",
                params={"fallback_only": "true"},
            )
            response.raise_for_status()
            quote = response.json()
            if not isinstance(quote, dict):
                return symbol, None
            price = float(quote.get("ltp") or 0)
            return (symbol, round(price, 2)) if price > 0 else (symbol, None)
        except (httpx.HTTPError, AttributeError, TypeError, ValueError) as error:
            print(f"Demo quote unavailable for {symbol}: {error}")
            return symbol, None
