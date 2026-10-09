"""Deterministic local mock broker for the StockItUp demo."""

import asyncio
import json
import os
import random
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

app = FastAPI(title="StockItUp Mock Broker API", version="2.0.0")
INDIA_TZ = ZoneInfo("Asia/Kolkata")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Legacy safety switch: reject startup if an old deployment tries to enable
# a live path that this mock broker does not implement.
USE_REAL_API = os.getenv("USE_REAL_API", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

MOCK_PORTFOLIO = {
    "account_id": "ACC-021-DEMO",
    "account_name": "Om Ekbote",
    "funds_available": 2_500_000.0,
    "funds_used": 500_000.0,
    "total_value": 3_000_000.0,
}

MOCK_POSITIONS = {
    "RELIANCE.NS": {"quantity": 50, "avg_price": 2840.0, "side": "LONG"},
    "INFY.NS": {"quantity": 100, "avg_price": 1780.0, "side": "LONG"},
    "TCS.NS": {"quantity": 25, "avg_price": 4120.0, "side": "LONG"},
    "HDFCBANK.NS": {"quantity": 75, "avg_price": 1650.0, "side": "LONG"},
}

MOCK_ORDERS: dict = {}

FALLBACK_PRICES = {
    "RELIANCE.NS": 2905.50,
    "INFY.NS": 1823.40,
    "TCS.NS": 4215.75,
    "HDFCBANK.NS": 1698.20,
    "WIPRO.NS": 567.85,
    "SBIN.NS": 832.60,
}

MOCK_INSTRUMENTS = {
    "RELIANCE.NS": {"name": "Reliance Industries Ltd", "exchange": "NSE", "token": 2885},
    "INFY.NS": {"name": "Infosys Ltd", "exchange": "NSE", "token": 1594},
    "TCS.NS": {"name": "Tata Consultancy Services", "exchange": "NSE", "token": 11536},
    "HDFCBANK.NS": {"name": "HDFC Bank Ltd", "exchange": "NSE", "token": 1333},
    "WIPRO.NS": {"name": "Wipro Ltd", "exchange": "NSE", "token": 3787},
    "SBIN.NS": {"name": "State Bank of India", "exchange": "NSE", "token": 3045},
}

redis_client: Optional[aioredis.Redis] = None


def client_order_key(client_order_id: str) -> str:
    return f"mock:order:client:{client_order_id}"


async def load_mock_order(client_order_id: str) -> Optional[dict]:
    if redis_client:
        raw = await redis_client.get(client_order_key(client_order_id))
        if raw:
            return json.loads(raw)
    return next(
        (order for order in MOCK_ORDERS.values() if order["client_order_id"] == client_order_id),
        None,
    )


async def load_mock_orders() -> list[dict]:
    """Load durable simulated orders for account and position projections."""
    orders = {order["client_order_id"]: order for order in MOCK_ORDERS.values()}
    if redis_client:
        client_order_ids = await redis_client.smembers("mock:order_ids")
        if client_order_ids:
            raw_orders = await redis_client.mget(
                [client_order_key(client_order_id) for client_order_id in client_order_ids]
            )
            for raw in raw_orders:
                if raw:
                    order = json.loads(raw)
                    orders[order["client_order_id"]] = order
    return list(orders.values())


async def get_portfolio_snapshot() -> tuple[float, dict[str, dict]]:
    """Project filled mock trades onto the fixed seed portfolio."""
    funds_available = float(MOCK_PORTFOLIO["funds_available"])
    positions = {symbol: dict(position) for symbol, position in MOCK_POSITIONS.items()}

    orders = await load_mock_orders()
    orders.sort(key=lambda order: order.get("created_at", ""))
    for order in orders:
        quantity = int(order.get("filled_quantity") or 0)
        price = float(order.get("average_price") or 0)
        if order.get("status") not in {"FILLED", "PARTIAL"} or quantity <= 0 or price <= 0:
            continue

        symbol = order["symbol"]
        position = positions.get(symbol, {"quantity": 0, "avg_price": 0.0, "side": "LONG"})
        held_quantity = int(position["quantity"])
        if order["side"] == "BUY":
            new_quantity = held_quantity + quantity
            position["avg_price"] = (
                (held_quantity * float(position["avg_price"]) + quantity * price) / new_quantity
            )
            position["quantity"] = new_quantity
            funds_available -= quantity * price
            positions[symbol] = position
        else:
            # The demo broker does not support opening short positions.
            sold_quantity = min(quantity, held_quantity)
            position["quantity"] = held_quantity - sold_quantity
            funds_available += sold_quantity * price
            if position["quantity"] == 0:
                positions.pop(symbol, None)
            else:
                positions[symbol] = position

    return funds_available, positions


def matches_order_intent(existing: dict, request: "PlaceOrderRequest") -> bool:
    """An idempotency key may be retried only for the exact same order."""
    if any(existing.get(field) != getattr(request, field) for field in (
        "symbol", "side", "order_type", "quantity"
    )):
        return False
    for field in ("price", "trigger_price"):
        previous = existing.get(field)
        requested = getattr(request, field)
        if previous is None or requested is None:
            if previous is not None or requested is not None:
                return False
        elif float(previous) != float(requested):
            return False
    return True


# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    global redis_client

    if USE_REAL_API:
        raise RuntimeError(
            "Live 021 trading is not integrated. Set USE_REAL_API=false; refusing to start rather than falling back to mock data."
        )

    print("=" * 60)
    print("StockItUp Mock Broker API Starting...")
    print("Mode: MOCK DATA")
    print("=" * 60)

    # Connect to Redis
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        redis_client = aioredis.from_url(redis_url, decode_responses=True)
        await redis_client.ping()
        print("✅ Redis connected")
    except Exception as e:
        print(f"⚠️  Redis not available: {e}")
        redis_client = None


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

async def get_mock_price(symbol: str) -> float:
    """Get price from Redis/yfinance or fallback."""
    if redis_client:
        try:
            val = await redis_client.get(f"price:{symbol}")
            if val:
                return float(val)
        except Exception:
            pass
    # Keep fallback quotes stable so the sidebar, chat, and approval preview
    # read the same demo prices when the external price feed is unavailable.
    return float(FALLBACK_PRICES.get(symbol, 1000.0))


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class PlaceOrderRequest(BaseModel):
    client_order_id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(pattern=r"^(RELIANCE|INFY|TCS|HDFCBANK|WIPRO|SBIN)\.NS$")
    side: str = Field(pattern=r"^(BUY|SELL)$")
    order_type: str = Field(pattern=r"^(MARKET|LIMIT|SL|SL-M)$")
    quantity: int = Field(gt=0, le=1000)
    price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    trigger_price: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_required_order_prices(self):
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("LIMIT orders require a positive price")
        if self.order_type in {"SL", "SL-M"} and self.trigger_price is None:
            raise ValueError("Stop orders require a positive trigger price")
        return self


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "syrus-mock-broker",
        "mode": "mock",
        "authenticated": None,
        "ts": datetime.now(timezone.utc).isoformat()
    }


@app.get("/account")
async def get_account():
    """Get account summary."""
    funds_available, positions = await get_portfolio_snapshot()
    # Mock response
    total_position_value = 0.0
    for symbol, pos in positions.items():
        price = await get_mock_price(symbol)
        total_position_value += price * pos["quantity"]

    return {
        "account_id": MOCK_PORTFOLIO["account_id"],
        "account_name": MOCK_PORTFOLIO["account_name"],
        "funds_available": round(funds_available, 2),
        "funds_used": MOCK_PORTFOLIO["funds_used"],
        "position_value": round(total_position_value, 2),
        "total_value": round(funds_available + total_position_value, 2),
        "currency": "INR",
    }


@app.get("/positions")
async def get_positions():
    """Get current positions."""
    # Mock response
    _, portfolio_positions = await get_portfolio_snapshot()
    positions = []
    for symbol, pos in portfolio_positions.items():
        ltp = await get_mock_price(symbol)
        pnl = (ltp - pos["avg_price"]) * pos["quantity"]
        pnl_pct = ((ltp - pos["avg_price"]) / pos["avg_price"]) * 100
        positions.append({
            "symbol": symbol,
            "quantity": pos["quantity"],
            "side": pos["side"],
            "avg_price": pos["avg_price"],
            "ltp": ltp,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "current_value": round(ltp * pos["quantity"], 2),
        })
    return {"positions": positions}


@app.get("/quote/{symbol}")
async def get_quote(symbol: str, fallback_only: bool = False):
    """Get a cached market price or a fixed demo fallback; orders always stay mock."""
    symbol = symbol.upper()
    if symbol not in MOCK_INSTRUMENTS:
        raise HTTPException(status_code=404, detail=f"Unsupported instrument: {symbol}")

    cached_price = (
        await redis_client.get(f"price:{symbol}")
        if redis_client and not fallback_only
        else None
    )
    price = (
        float(FALLBACK_PRICES[symbol])
        if fallback_only
        else await get_mock_price(symbol)
    )
    snapshot = {}
    if redis_client and not fallback_only:
        raw_snapshot = await redis_client.get("price:snapshot")
        if raw_snapshot:
            snapshot = json.loads(raw_snapshot)
    spread = round(price * 0.0001, 2)
    return {
        "symbol": symbol,
        "ltp": price,
        "market_data_source": (
            "fixed_demo_fallback"
            if fallback_only
            else snapshot.get("sources", {}).get(symbol)
            or ("yahoo_finance_cache" if cached_price else "fixed_demo_fallback")
        ),
        "broker_mode": "mock",
        "bid": round(price - spread, 2),
        "ask": round(price + spread, 2),
        "open": round(price * random.uniform(0.995, 1.005), 2),
        "high": round(price * random.uniform(1.001, 1.012), 2),
        "low": round(price * random.uniform(0.988, 0.999), 2),
        "prev_close": round(price * random.uniform(0.993, 1.007), 2),
        "volume": random.randint(50_000, 5_000_000),
        "timestamp": snapshot.get("updated_at") if cached_price else datetime.now(timezone.utc).isoformat(),
    }


@app.get("/orders")
async def get_orders(status: str = Query(default="ALL")):
    """Get order history."""
    # Load durable mock order records so reconciliation survives a broker restart.
    orders_by_client_id = {o["client_order_id"]: o for o in MOCK_ORDERS.values()}
    if redis_client:
        client_order_ids = await redis_client.smembers("mock:order_ids")
        if client_order_ids:
            raw_orders = await redis_client.mget([client_order_key(order_id) for order_id in client_order_ids])
            for raw in raw_orders:
                if raw:
                    order = json.loads(raw)
                    orders_by_client_id[order["client_order_id"]] = order
    orders = list(orders_by_client_id.values())
    if status != "ALL":
        orders = [o for o in orders if o["status"] == status]
    orders.sort(key=lambda o: o["created_at"], reverse=True)
    return {"orders": orders, "total": len(orders)}


def build_daily_trade_report(orders: list[dict], today: date | None = None) -> dict:
    """Build a factual daily summary; no P&L is inferred from incomplete demo history."""
    report_date = today or datetime.now(INDIA_TZ).date()
    todays_orders = []
    for order in orders:
        raw_created = order.get("created_at")
        try:
            created = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created.astimezone(INDIA_TZ).date() == report_date:
            todays_orders.append(order)

    filled = [order for order in todays_orders if order.get("status") in {"FILLED", "PARTIAL"}]
    sides = {
        side: [order for order in filled if order.get("side") == side]
        for side in ("BUY", "SELL")
    }
    filled_quantity = sum(int(order.get("filled_quantity") or 0) for order in filled)
    turnover = sum(
        float(order.get("average_price") or 0) * int(order.get("filled_quantity") or 0)
        for order in filled
    )
    return {
        "source": "local mock broker",
        "mode": "demo",
        "date_ist": report_date.isoformat(),
        "total_orders": len(todays_orders),
        "filled_orders": len(filled),
        "buy_orders": len(sides["BUY"]),
        "sell_orders": len(sides["SELL"]),
        "filled_shares": filled_quantity,
        "filled_turnover": round(turnover, 2),
        "rejected_orders": sum(order.get("status") == "REJECTED" for order in todays_orders),
        "cancelled_orders": sum(order.get("status") == "CANCELLED" for order in todays_orders),
        "pending_orders": sum(order.get("status") in {"PROCESSING", "SUBMITTED"} for order in todays_orders),
        "realized_pnl": None,
        "orders": [
            {
                key: order.get(key)
                for key in ("symbol", "side", "order_type", "quantity", "filled_quantity", "average_price", "status", "created_at")
            }
            for order in todays_orders
        ],
    }


@app.get("/reports/daily")
async def daily_trade_report():
    history = await get_orders(status="ALL")
    return build_daily_trade_report(history["orders"])


@app.get("/orders/by-client-id/{client_order_id}")
async def get_order_by_client_id(client_order_id: str):
    """Find one order by its idempotency key for safe reconciliation."""
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Durable order store is unavailable")
    order = await load_mock_order(client_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="No order found for this client order ID")
    if order.get("status") == "PROCESSING":
        return JSONResponse(status_code=202, content=order)
    return order


@app.post("/orders")
async def place_order(req: PlaceOrderRequest):
    """Place an order."""
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Durable order store is unavailable; no order was submitted")

    symbol = req.symbol.upper()
    order_key = client_order_key(req.client_order_id)
    existing = await load_mock_order(req.client_order_id)
    if existing:
        if not matches_order_intent(existing, req):
            raise HTTPException(status_code=409, detail="This client order ID is already bound to a different order intent")
        if existing.get("status") == "PROCESSING":
            raise HTTPException(status_code=409, detail="Order outcome is still processing; reconcile by client order ID")
        return existing

    intent = {
        "client_order_id": req.client_order_id,
        "symbol": symbol,
        "side": req.side,
        "order_type": req.order_type,
        "quantity": req.quantity,
        "price": req.price,
        "trigger_price": req.trigger_price,
        "status": "PROCESSING",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    claimed = await redis_client.set(order_key, json.dumps(intent), nx=True)
    if not claimed:
        existing = await load_mock_order(req.client_order_id)
        if existing:
            if not matches_order_intent(existing, req):
                raise HTTPException(status_code=409, detail="This client order ID is already bound to a different order intent")
            if existing.get("status") != "PROCESSING":
                return existing
        raise HTTPException(status_code=409, detail="Order submission is already in progress; reconcile by client order ID")
    await redis_client.sadd("mock:order_ids", req.client_order_id)

    # The idempotency intent is durable before simulated execution begins.
    ltp = await get_mock_price(symbol)

    # Simulate execution
    exchange_order_id = f"NSE{random.randint(100000000, 999999999)}"
    if req.quantity == 1:
        fill_scenario = random.choices(["FILLED", "REJECTED"], weights=[95, 5])[0]
    else:
        fill_scenario = random.choices(["FILLED", "PARTIAL", "REJECTED"], weights=[85, 10, 5])[0]

    if fill_scenario == "FILLED":
        slippage = ltp * random.uniform(-0.0005, 0.0005)
        avg_price = round(ltp + slippage, 2)
        filled_qty = req.quantity
        status = "FILLED"
    elif fill_scenario == "PARTIAL":
        slippage = ltp * random.uniform(-0.001, 0.001)
        avg_price = round(ltp + slippage, 2)
        filled_qty = random.randint(1, req.quantity - 1)
        status = "PARTIAL"
    else:
        avg_price = None
        filled_qty = 0
        status = "REJECTED"

    order = {
        "order_id": str(uuid.uuid4()),
        "client_order_id": req.client_order_id,
        "exchange_order_id": exchange_order_id,
        "symbol": symbol,
        "side": req.side,
        "order_type": req.order_type,
        "quantity": req.quantity,
        "price": req.price,
        "trigger_price": req.trigger_price,
        "filled_quantity": filled_qty,
        "average_price": avg_price,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "filled_at": datetime.now(timezone.utc).isoformat() if fill_scenario != "REJECTED" else None,
        "reject_reason": "Insufficient liquidity" if fill_scenario == "REJECTED" else None,
    }

    MOCK_ORDERS[order["order_id"]] = order
    await redis_client.set(order_key, json.dumps(order))
    return order


@app.get("/instruments")
async def get_instruments(search: str = Query(default="")):
    """Search the supported demo instrument catalog."""
    instruments = dict(MOCK_INSTRUMENTS)

    if search:
        search = search.upper()
        instruments = {k: v for k, v in instruments.items() if search in k or search in v["name"].upper()}

    return {"instruments": instruments}
