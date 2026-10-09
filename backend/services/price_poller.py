"""Publish clearly labeled demo quotes from the local mock broker to Redis."""
import asyncio
import json
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis

from config import settings
from services.instruments import INSTRUMENTS

SYMBOL_ALIAS = {"^NSEI": "NIFTY50"}
POLL_INTERVAL = 15  # seconds; refreshes quote freshness for the demo workflow


class PricePoller:
    def __init__(self, redis: aioredis.Redis):
        self.redis = redis
        self._running = False
        self.first_snapshot = asyncio.Event()

    async def start(self):
        """Refresh the mock quote cache until the application shuts down."""
        self._running = True
        print("Demo quote poller: starting first fetch...")
        while self._running:
            try:
                await self._fetch_and_cache()
            except Exception as error:
                print(f"Demo quote poller error: {error}")
            await asyncio.sleep(POLL_INTERVAL)

    def stop(self):
        self._running = False

    async def _fetch_and_cache(self):
        """Load fixed mock quotes without waiting on an external market feed."""
        async with httpx.AsyncClient(timeout=5.0) as http:
            results = await asyncio.gather(
                *(self._get_demo_quote(http, symbol) for symbol in INSTRUMENTS)
            )
        prices = {symbol: price for symbol, price in results if price is not None}

        if not prices:
            print("Demo quote poller: mock broker returned no prices")
            return

        snapshot = {}
        sources = {}
        pipe = self.redis.pipeline()
        for symbol, price in prices.items():
            redis_key = SYMBOL_ALIAS.get(symbol, symbol)
            pipe.set(f"price:{redis_key}", str(price), ex=60)
            snapshot[redis_key] = price
            sources[redis_key] = "fixed_demo_fallback"

        pipe.set(
            "price:snapshot",
            json.dumps({
                "prices": snapshot,
                "sources": sources,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }),
            ex=60,
        )

        await pipe.execute()
        self.first_snapshot.set()
        print(f"Demo quotes updated: {', '.join(f'{symbol}={price}' for symbol, price in snapshot.items())}")

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
