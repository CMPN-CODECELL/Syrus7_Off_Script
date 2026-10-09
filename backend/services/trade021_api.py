"""
021 Trade API Service
Complete integration with 021 Trade Developer API

Authentication: Bearer token (get via /auth/token)
Base URL: https://devapi.021.trade/api/developer-api/v1

Key features:
- Token-based authentication
- Real-time market data via REST and WebSocket
- Order management (place, modify, cancel)
- Portfolio and positions tracking
- Instrument search
"""

import json
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import httpx
from pydantic import BaseModel


class TradeAPIError(Exception):
    """Custom exception for 021 Trade API errors."""
    pass


class OrderRequest(BaseModel):
    """Order placement request model."""
    exchange: str  # NSE, BSE, NSEFO, BSEFO
    token: int  # Instrument token
    qty: int  # Positive for buy, negative for sell
    price: int = 0  # In paise (0 = market order)
    book: str = "RL"  # RL (regular) or SL (stop-loss)
    trigger: int = 0  # Trigger price in paise (for SL orders)
    discQuantity: int = 0  # Disclosed quantity
    product: str = "INTRADAY"  # INTRADAY, CNC, NRML
    validity: str = "Day"  # Day or IOC
    amo: bool = False  # After-market order


class Trade021APIClient:
    """
    021 Trade API Client

    Handles authentication and all API interactions with 021 Trade platform.
    """

    def __init__(self, username: str, password: str, base_url: str = None):
        """
        Initialize the 021 Trade API client.

        Args:
            username: Your UCC (e.g., HACK1234)
            password: Your sign-up password
            base_url: Optional custom base URL (defaults to production)
        """
        self.username = username
        self.password = password
        self.base_url = base_url or "https://devapi.021.trade/api/developer-api/v1"
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[str] = None
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        """Context manager entry."""
        await self.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.http_client.aclose()

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()

    async def login(self) -> Dict:
        """
        Authenticate and get access token.
        Token is valid until next 5 AM IST.

        Returns:
            Dict with accessToken and expiresAt
        """
        url = f"{self.base_url}/auth/token"
        payload = {
            "username": self.username,
            "password": self.password
        }

        try:
            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                self.access_token = data["data"]["accessToken"]
                self.token_expires_at = data["data"].get("expiresAt")
                return data["data"]
            else:
                raise TradeAPIError(f"Login failed: {data.get('message', 'Unknown error')}")

        except httpx.HTTPStatusError as e:
            raise TradeAPIError(f"Login HTTP error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise TradeAPIError(f"Login error: {str(e)}")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with bearer token."""
        if not self.access_token:
            raise TradeAPIError("Not authenticated. Call login() first.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    # -------------------------------------------------------------------------
    # Orders API
    # -------------------------------------------------------------------------

    async def place_order(self, order: OrderRequest) -> Dict:
        """
        Place an order.

        Args:
            order: OrderRequest with all order details

        Returns:
            Dict with orderId and status
        """
        url = f"{self.base_url}/orders"

        try:
            response = await self.http_client.post(
                url,
                json=order.dict(),
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise TradeAPIError(f"Place order error: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            raise TradeAPIError(f"Place order error: {str(e)}")

    async def modify_order(self, order_id: str, order: OrderRequest) -> Dict:
        """Modify a pending order."""
        url = f"{self.base_url}/orders/{order_id}"

        try:
            response = await self.http_client.put(
                url,
                json=order.dict(),
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise TradeAPIError(f"Modify order error: {str(e)}")

    async def cancel_order(self, order_id: str, exchange: str, token: int, product: str) -> Dict:
        """Cancel a pending order."""
        url = f"{self.base_url}/orders/{order_id}"
        payload = {
            "exchange": exchange,
            "token": token,
            "product": product
        }

        try:
            response = await self.http_client.delete(
                url,
                json=payload,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise TradeAPIError(f"Cancel order error: {str(e)}")

    async def get_orders(self) -> List[Dict]:
        """Get all today's orders."""
        url = f"{self.base_url}/orders"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                return data["data"]
            return []
        except Exception as e:
            raise TradeAPIError(f"Get orders error: {str(e)}")

    async def get_order(self, order_id: str) -> Optional[Dict]:
        """Get details of a specific order."""
        url = f"{self.base_url}/orders/{order_id}"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                orders = data["data"]
                return orders[0] if orders else None
            return None
        except Exception as e:
            raise TradeAPIError(f"Get order error: {str(e)}")

    # -------------------------------------------------------------------------
    # Trades API
    # -------------------------------------------------------------------------

    async def get_trades(self) -> List[Dict]:
        """Get all today's trades (fills)."""
        url = f"{self.base_url}/trades"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                return data["data"]
            return []
        except Exception as e:
            raise TradeAPIError(f"Get trades error: {str(e)}")

    async def get_order_trades(self, order_id: str) -> List[Dict]:
        """Get fills of a specific order."""
        url = f"{self.base_url}/orders/{order_id}/trades"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                return data["data"]
            return []
        except Exception as e:
            raise TradeAPIError(f"Get order trades error: {str(e)}")

    # -------------------------------------------------------------------------
    # Portfolio API
    # -------------------------------------------------------------------------

    async def get_positions(self) -> List[Dict]:
        """Get today's positions plus F&O carried forward."""
        url = f"{self.base_url}/portfolio/positions"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                return data["data"]
            return []
        except Exception as e:
            raise TradeAPIError(f"Get positions error: {str(e)}")

    async def get_holdings(self) -> List[Dict]:
        """Get delivery holdings in demat."""
        url = f"{self.base_url}/portfolio/holdings"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                return data["data"]
            return []
        except Exception as e:
            raise TradeAPIError(f"Get holdings error: {str(e)}")

    # -------------------------------------------------------------------------
    # Market Data API
    # -------------------------------------------------------------------------

    async def get_instruments(self) -> bytes:
        """
        Get full instrument list as gzipped CSV.
        Returns raw bytes that need to be decompressed.
        """
        url = f"{self.base_url}/instruments"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            return response.content
        except Exception as e:
            raise TradeAPIError(f"Get instruments error: {str(e)}")

    async def generate_ephemeral_key(self) -> str:
        """
        Generate ephemeral key for WebSocket connections.
        Valid for 24 hours.
        """
        url = f"{self.base_url}/websocket/ephemeral-key"

        try:
            response = await self.http_client.get(url, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            if data.get("success") and data.get("data"):
                return data["data"]["token"]
            raise TradeAPIError("Failed to generate ephemeral key")
        except Exception as e:
            raise TradeAPIError(f"Generate ephemeral key error: {str(e)}")


# -----------------------------------------------------------------------------
# Convenience functions for common operations
# -----------------------------------------------------------------------------

async def create_market_buy_order(
    client: Trade021APIClient,
    symbol_token: int,
    quantity: int,
    exchange: str = "NSE",
    product: str = "INTRADAY"
) -> Dict:
    """
    Helper to create a simple market buy order.

    Args:
        client: Authenticated Trade021APIClient
        symbol_token: Instrument token from instruments CSV
        quantity: Number of shares to buy
        exchange: NSE, BSE, NSEFO, or BSEFO
        product: INTRADAY, CNC, or NRML
    """
    order = OrderRequest(
        exchange=exchange,
        token=symbol_token,
        qty=quantity,  # Positive = buy
        price=0,  # Market order
        product=product
    )
    return await client.place_order(order)


async def create_market_sell_order(
    client: Trade021APIClient,
    symbol_token: int,
    quantity: int,
    exchange: str = "NSE",
    product: str = "INTRADAY"
) -> Dict:
    """Helper to create a simple market sell order."""
    order = OrderRequest(
        exchange=exchange,
        token=symbol_token,
        qty=-quantity,  # Negative = sell
        price=0,  # Market order
        product=product
    )
    return await client.place_order(order)


async def create_limit_order(
    client: Trade021APIClient,
    symbol_token: int,
    quantity: int,
    limit_price: float,
    is_buy: bool = True,
    exchange: str = "NSE",
    product: str = "INTRADAY"
) -> Dict:
    """
    Helper to create a limit order.

    Args:
        limit_price: Price in rupees (will be converted to paise)
    """
    price_paise = int(limit_price * 100)
    order = OrderRequest(
        exchange=exchange,
        token=symbol_token,
        qty=quantity if is_buy else -quantity,
        price=price_paise,
        product=product
    )
    return await client.place_order(order)
