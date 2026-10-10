# Market data configuration

Market data and order execution are separate integrations. The default is `demo`: the app reads fixed quotes from the local mock broker and clearly labels them as demo data. Set `MARKET_DATA_PROVIDER=yahoo` to read quotes and historical price series from the existing Yahoo Finance adapter. This changes quote data only; order execution remains on the mock broker and still requires explicit approval.

## Enable Yahoo Finance data in Docker Compose

In PowerShell, from the project directory:

```powershell
$env:MARKET_DATA_PROVIDER = "yahoo"
docker compose up -d --build backend
```

The setting is read by the backend container at startup. To return to the local demo feed:

```powershell
$env:MARKET_DATA_PROVIDER = "demo"
docker compose up -d --build backend
```

You can instead put `MARKET_DATA_PROVIDER=yahoo` in the shell environment used to run Compose. `.env.example` documents the default. Do not put provider secrets in frontend environment variables.

## API surface

- `GET /chat/price-snapshot` returns the latest available quotes with `provider`, `mode`, and `updated_at` metadata.
- `GET /market/history/{symbol}?days=30` returns historical close points for the selected market chart. `days` accepts 1–365.
- Yahoo Finance quotes may be delayed, rate-limited, or temporarily unavailable. In Yahoo mode the app does not fill missing values with demo prices; inspect the feed status and try again later.
- Demo history is built only from quote snapshots observed while the app is running. It is not backfilled or presented as historical market data.

## Provider and trading safety

The Yahoo adapter in `backend/services/stock_data_service.py` uses `yfinance` and does not require a key. Other provider adapter classes in that file are templates and are not selectable through `MARKET_DATA_PROVIDER` yet. For a licensed feed, implement its quote and history methods in the backend adapter and map its symbols there.

The mock broker continues to own portfolio, order preparation, approval, and execution status. A quote-provider change never enables live brokerage execution. The dashboard must continue to label mock-broker orders as demo/simulated; only a separately integrated broker can report real execution.
