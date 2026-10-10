"""
Real Stock Data Integration Service

This service provides a unified interface to fetch real-time stock data.
Replace the implementation based on your actual API provider.

Supported providers (uncomment and configure the one you're using):
- Alpha Vantage (free tier available)
- Twelve Data (free tier available)
- Yahoo Finance (via yfinance - current implementation)
- Zerodha Kite (requires broker account)
- Upstox (requires broker account)
- Dhan (requires broker account)
- 5paisa (requires broker account)
- Your custom API
"""

import asyncio
from typing import Dict, Optional, List
import httpx
from datetime import datetime
import yfinance as yf


class StockDataProvider:
    """Base class for stock data providers."""

    async def get_quote(self, symbol: str) -> Dict:
        """Get current quote for a symbol."""
        raise NotImplementedError

    async def get_historical_data(self, symbol: str, days: int = 30) -> List[Dict]:
        """Get historical price data."""
        raise NotImplementedError

    async def search_symbol(self, query: str) -> List[Dict]:
        """Search for symbols/instruments."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# OPTION 1: Yahoo Finance (FREE - Current Implementation)
# ---------------------------------------------------------------------------

class YahooFinanceProvider(StockDataProvider):
    """
    Uses yfinance library (free, no API key needed).
    Good for: NSE, BSE, US stocks.
    Limitations: Rate limits may apply, unofficial API.
    """

    async def get_quote(self, symbol: str) -> Dict:
        """Get real-time quote from Yahoo Finance."""
        try:
            # Run synchronous yfinance in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
            info = await loop.run_in_executor(None, lambda: ticker.info)

            # Get fast info for real-time data
            fast_info = await loop.run_in_executor(None, lambda: ticker.fast_info)

            return {
                "symbol": symbol,
                "ltp": fast_info.get('last_price', info.get('currentPrice', 0)),
                "open": info.get('open', 0),
                "high": info.get('dayHigh', 0),
                "low": info.get('dayLow', 0),
                "prev_close": info.get('previousClose', 0),
                "volume": info.get('volume', 0),
                "bid": info.get('bid', 0),
                "ask": info.get('ask', 0),
                "timestamp": datetime.utcnow().isoformat(),
                "provider": "yahoo_finance"
            }
        except Exception as e:
            raise Exception(f"Yahoo Finance error: {str(e)}")

    async def get_historical_data(self, symbol: str, days: int = 30) -> List[Dict]:
        """Get historical price data."""
        try:
            loop = asyncio.get_event_loop()
            ticker = await loop.run_in_executor(None, yf.Ticker, symbol)
            interval = "5m" if days <= 1 else "30m" if days <= 30 else "1d"
            hist = await loop.run_in_executor(None, lambda: ticker.history(period=f"{days}d", interval=interval))

            data = []
            for date, row in hist.iterrows():
                data.append({
                    "date": date.isoformat(),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": int(row['Volume'])
                })
            return data
        except Exception as e:
            raise Exception(f"Historical data error: {str(e)}")

    async def search_symbol(self, query: str) -> List[Dict]:
        """Search for symbols - limited functionality with yfinance."""
        # yfinance doesn't have search, return common NSE stocks
        nse_stocks = {
            "RELIANCE": "RELIANCE.NS",
            "INFY": "INFY.NS",
            "TCS": "TCS.NS",
            "HDFCBANK": "HDFCBANK.NS",
            "ICICIBANK": "ICICIBANK.NS",
            "SBIN": "SBIN.NS",
            "WIPRO": "WIPRO.NS",
            "BAJFINANCE": "BAJFINANCE.NS",
            "AXISBANK": "AXISBANK.NS",
        }

        query = query.upper()
        results = []
        for name, symbol in nse_stocks.items():
            if query in name or query in symbol:
                results.append({
                    "symbol": symbol,
                    "name": name,
                    "exchange": "NSE"
                })
        return results


# ---------------------------------------------------------------------------
# OPTION 2: Alpha Vantage (FREE tier available)
# ---------------------------------------------------------------------------

class AlphaVantageProvider(StockDataProvider):
    """
    Alpha Vantage API - Free tier: 25 requests/day, 5 requests/minute.
    Get your free API key from: https://www.alphavantage.co/support/#api-key

    Best for: Real-time quotes, historical data, technical indicators.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.alphavantage.co/query"

    async def get_quote(self, symbol: str) -> Dict:
        """Get real-time quote from Alpha Vantage."""
        async with httpx.AsyncClient() as client:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.api_key
            }
            response = await client.get(self.base_url, params=params)
            data = response.json()

            if "Global Quote" in data:
                quote = data["Global Quote"]
                return {
                    "symbol": symbol,
                    "ltp": float(quote.get("05. price", 0)),
                    "open": float(quote.get("02. open", 0)),
                    "high": float(quote.get("03. high", 0)),
                    "low": float(quote.get("04. low", 0)),
                    "prev_close": float(quote.get("08. previous close", 0)),
                    "volume": int(quote.get("06. volume", 0)),
                    "timestamp": quote.get("07. latest trading day"),
                    "provider": "alpha_vantage"
                }
            raise Exception("Invalid response from Alpha Vantage")

    async def search_symbol(self, query: str) -> List[Dict]:
        """Search for symbols."""
        async with httpx.AsyncClient() as client:
            params = {
                "function": "SYMBOL_SEARCH",
                "keywords": query,
                "apikey": self.api_key
            }
            response = await client.get(self.base_url, params=params)
            data = response.json()

            results = []
            for match in data.get("bestMatches", [])[:10]:
                results.append({
                    "symbol": match.get("1. symbol"),
                    "name": match.get("2. name"),
                    "exchange": match.get("4. region")
                })
            return results


# ---------------------------------------------------------------------------
# OPTION 3: Twelve Data (FREE tier available)
# ---------------------------------------------------------------------------

class TwelveDataProvider(StockDataProvider):
    """
    Twelve Data API - Free tier: 800 requests/day.
    Get your free API key from: https://twelvedata.com/pricing

    Best for: Real-time data, multiple exchanges, crypto, forex.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.twelvedata.com"

    async def get_quote(self, symbol: str) -> Dict:
        """Get real-time quote from Twelve Data."""
        async with httpx.AsyncClient() as client:
            params = {
                "symbol": symbol,
                "apikey": self.api_key
            }
            response = await client.get(f"{self.base_url}/quote", params=params)
            data = response.json()

            return {
                "symbol": symbol,
                "ltp": float(data.get("close", 0)),
                "open": float(data.get("open", 0)),
                "high": float(data.get("high", 0)),
                "low": float(data.get("low", 0)),
                "prev_close": float(data.get("previous_close", 0)),
                "volume": int(data.get("volume", 0)),
                "timestamp": data.get("datetime"),
                "provider": "twelve_data"
            }

    async def search_symbol(self, query: str) -> List[Dict]:
        """Search for symbols."""
        async with httpx.AsyncClient() as client:
            params = {
                "symbol": query,
                "apikey": self.api_key
            }
            response = await client.get(f"{self.base_url}/symbol_search", params=params)
            data = response.json()

            results = []
            for item in data.get("data", [])[:10]:
                results.append({
                    "symbol": item.get("symbol"),
                    "name": item.get("instrument_name"),
                    "exchange": item.get("exchange")
                })
            return results


# ---------------------------------------------------------------------------
# OPTION 4: Custom API Template
# ---------------------------------------------------------------------------

class CustomAPIProvider(StockDataProvider):
    """
    Template for integrating your own stock data API.
    Replace the implementation with your actual API calls.
    """

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            # Add other headers as needed
        }

    async def get_quote(self, symbol: str) -> Dict:
        """Get real-time quote from your custom API."""
        async with httpx.AsyncClient() as client:
            # Replace with your actual API endpoint
            response = await client.get(
                f"{self.base_url}/quote/{symbol}",
                headers=self.headers
            )
            data = response.json()

            # Map your API response to standard format
            return {
                "symbol": symbol,
                "ltp": data.get("last_price"),  # Adjust field names
                "open": data.get("open"),
                "high": data.get("high"),
                "low": data.get("low"),
                "prev_close": data.get("previous_close"),
                "volume": data.get("volume"),
                "bid": data.get("bid"),
                "ask": data.get("ask"),
                "timestamp": data.get("timestamp"),
                "provider": "custom_api"
            }

    async def search_symbol(self, query: str) -> List[Dict]:
        """Search for symbols."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/search",
                params={"q": query},
                headers=self.headers
            )
            data = response.json()

            # Map your API response
            return [
                {
                    "symbol": item.get("symbol"),
                    "name": item.get("name"),
                    "exchange": item.get("exchange")
                }
                for item in data.get("results", [])
            ]


# ---------------------------------------------------------------------------
# Provider Factory
# ---------------------------------------------------------------------------

def get_stock_provider(provider_type: str = "yahoo", **kwargs) -> StockDataProvider:
    """
    Factory function to get the configured stock data provider.

    Args:
        provider_type: One of "yahoo", "alpha_vantage", "twelve_data", "custom"
        **kwargs: Provider-specific configuration (api_key, base_url, etc.)

    Returns:
        StockDataProvider instance
    """
    if provider_type == "yahoo":
        return YahooFinanceProvider()

    elif provider_type == "alpha_vantage":
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("Alpha Vantage requires api_key")
        return AlphaVantageProvider(api_key)

    elif provider_type == "twelve_data":
        api_key = kwargs.get("api_key")
        if not api_key:
            raise ValueError("Twelve Data requires api_key")
        return TwelveDataProvider(api_key)

    elif provider_type == "custom":
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")
        if not api_key or not base_url:
            raise ValueError("Custom provider requires api_key and base_url")
        return CustomAPIProvider(api_key, base_url)

    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


# ---------------------------------------------------------------------------
# Convenience function for backward compatibility
# ---------------------------------------------------------------------------

async def get_live_quote(symbol: str, provider_type: str = "yahoo", **kwargs) -> Dict:
    """
    Get live quote using configured provider.

    Usage:
        # Yahoo Finance (default)
        quote = await get_live_quote("RELIANCE.NS")

        # Alpha Vantage
        quote = await get_live_quote("RELIANCE.NS", provider_type="alpha_vantage",
                                     api_key="YOUR_KEY")

        # Custom API
        quote = await get_live_quote("RELIANCE", provider_type="custom",
                                     api_key="YOUR_KEY", base_url="https://api.example.com")
    """
    provider = get_stock_provider(provider_type, **kwargs)
    return await provider.get_quote(symbol)
