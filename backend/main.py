"""
Syrus Backend — Main FastAPI Application
"""
from contextlib import asynccontextmanager
import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from config import settings
from db import AsyncSessionLocal, init_db
from services.price_poller import PricePoller
from services.standing_instructions import StandingInstructionRunner
from services.stock_data_service import get_stock_provider


# Global redis client shared across services
redis_client: aioredis.Redis = None
price_poller: PricePoller = None
instruction_runner: StandingInstructionRunner = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global redis_client, price_poller, instruction_runner

    # Connect Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis_client
    print("✅ Redis connected")

    # Init DB
    await init_db()
    print("✅ Database ready")

    # Start the local mock quote poller; it publishes fixed demo prices every 15s.
    price_poller = PricePoller(redis_client)
    poller_task = asyncio.create_task(price_poller.start())
    instruction_runner = StandingInstructionRunner(AsyncSessionLocal, redis_client)

    async def start_instruction_runner_after_first_quote():
        try:
            await asyncio.wait_for(price_poller.first_snapshot.wait(), timeout=30)
        except asyncio.TimeoutError:
            print("Price feed did not provide an initial snapshot; standing rules will pause on missing quotes.")
        await instruction_runner.start()

    instruction_task = asyncio.create_task(start_instruction_runner_after_first_quote())
    print("✅ Price poller started")

    yield  # App runs here

    # Cleanup
    price_poller.stop()
    instruction_runner.stop()
    poller_task.cancel()
    instruction_task.cancel()
    await asyncio.gather(poller_task, instruction_task, return_exceptions=True)
    await redis_client.aclose()
    print("Syrus backend shut down cleanly.")


app = FastAPI(
    title="Syrus AI Trading Copilot API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from routers import chat, orders, instructions, audit, risk_limits

app.include_router(chat.router,         prefix="/chat",         tags=["Chat"])
app.include_router(orders.router,       prefix="/orders",       tags=["Orders"])
app.include_router(instructions.router, prefix="/instructions", tags=["Standing Instructions"])
app.include_router(audit.router,        prefix="/audit",        tags=["Audit"])
app.include_router(risk_limits.router, prefix="/risk-limits",  tags=["Risk Budget"])


@app.get("/market/history/{symbol}")
async def market_history(symbol: str, days: int = Query(default=30, ge=1, le=365)):
    """Return chart points from provider history or quotes observed by this app."""
    cleaned = symbol.strip().upper()
    aliases = {"NIFTY 50": "^NSEI", "SENSEX": "^BSESN", "NIFTY50": "^NSEI"}
    provider_symbol = aliases.get(cleaned, cleaned)
    if not re.fullmatch(r"[A-Z0-9.^_-]{1,24}", provider_symbol):
        raise HTTPException(status_code=400, detail="Invalid market symbol.")
    if provider_symbol not in {"^NSEI", "^BSESN"} and "." not in provider_symbol:
        provider_symbol += ".NS"

    if settings.market_data_provider.lower() == "yahoo":
        try:
            provider = get_stock_provider("yahoo")
            points = await provider.get_historical_data(provider_symbol, days=days)
            points = [{"time": item["date"], "price": item["close"]} for item in points if item.get("close")]
            return {"symbol": provider_symbol, "provider": "yahoo_finance", "mode": "external_market_data", "points": points}
        except Exception as error:
            raise HTTPException(status_code=502, detail="Market history is unavailable from the configured provider.") from error

    redis = redis_client
    if redis is None:
        raise HTTPException(status_code=503, detail="Market data cache is not ready.")
    redis_symbol = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX"}.get(provider_symbol, provider_symbol)
    raw_points = await redis.lrange(f"market:history:{redis_symbol}", 0, -1)
    points = []
    for raw_point in raw_points:
        try:
            points.append(json.loads(raw_point))
        except (TypeError, ValueError):
            continue
    return {"symbol": redis_symbol, "provider": "fixed_demo_fallback", "mode": "demo", "points": points[-max(2, days * 20):]}


@app.get("/health")
async def health():
    """Liveness probe: the backend process can answer requests."""
    return {"status": "ok", "service": "syrus-backend"}


@app.get("/ready")
async def readiness():
    """Readiness probe for dependencies required by the mock trading flow."""
    checks = {
        "postgres": "down",
        "redis": "down",
        "mock_broker": "down",
        "market_data": "down",
    }

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        pass

    snapshot = None
    try:
        if redis_client is not None:
            await redis_client.ping()
            raw_snapshot = await redis_client.get("price:snapshot")
            snapshot = json.loads(raw_snapshot) if raw_snapshot else None
            checks["redis"] = "ok"
    except Exception:
        snapshot = None

    if isinstance(snapshot, dict) and isinstance(snapshot.get("updated_at"), str):
        try:
            updated_at = datetime.fromisoformat(snapshot["updated_at"].replace("Z", "+00:00"))
            age_seconds = (datetime.now(timezone.utc) - updated_at).total_seconds()
            if 0 <= age_seconds <= 180 and snapshot.get("prices"):
                checks["market_data"] = "ok"
        except (TypeError, ValueError):
            pass

    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            response = await http.get(f"{settings.mock_api_url}/health")
            response.raise_for_status()
            if response.json().get("mode") == "mock":
                checks["mock_broker"] = "ok"
    except (httpx.HTTPError, ValueError, AttributeError):
        pass

    if any(status != "ok" for status in checks.values()):
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks},
        )
    return {"status": "ready", "service": "syrus-backend", "mode": "mock", "checks": checks}


@app.get("/")
async def root():
    return {"message": "Syrus AI Trading Copilot — backend running"}
