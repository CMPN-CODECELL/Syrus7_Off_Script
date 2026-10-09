# StockItUp

### An AI trading copilot built around review, risk checks, and explicit approval.

StockItUp turns plain-language investing requests into clear portfolio answers and reviewable trade drafts. Gemini helps interpret what you ask; the backend validates the request, checks risk limits, and presents any proposed action for your approval.

> **Demo mode:** This repository runs against a local mock broker and sample portfolio. Quotes and fills are simulated. It is not connected to a live brokerage and must not be used to place real trades.

---

## What you can do

- **Ask portfolio questions** and request quotes for supported instruments.
- **Draft trades in natural language** and review the quote, quantity, estimated value, and risk checks before approval.
- **Review multi-order plans** as one grouped proposal, with preflight checks across all legs.
- **Create standing instruction drafts**, such as a proposed stop-loss rule, and explicitly activate or reject them.
- **Adjust supported risk limits** through a review-and-approval flow.
- **Inspect the audit history** of the app's recorded actions.

Every trade requires an explicit approval. The assistant cannot submit an order directly from chat.

## How it fits together

```text
Browser (Next.js)
       │
       ▼
FastAPI backend ─── Gemini API
       │
       ├── PostgreSQL: application records and audit history
       ├── Redis: shared state and coordination
       └── Mock broker: demo portfolio, quotes, and simulated orders
```

| Component | Purpose |
| --- | --- |
| `frontend/` | Next.js chat, portfolio view, and approval interfaces |
| `backend/` | FastAPI, Gemini tool flow, validation, risk checks, approvals, and order handling |
| `mock-api/` | Local demo portfolio, instrument prices, and simulated broker responses |
| `db/migrations/` | PostgreSQL schema initialization |

## Run with Docker Compose

### Prerequisites

- Docker Desktop with Docker Compose enabled
- A Gemini API key from Google AI Studio

### Start

1. From this directory, copy `.env.example` to `.env.local`.

   ```powershell
   Copy-Item .env.example .env.local
   ```

2. Open `.env.local` and set `GEMINI_API_KEY`. Replace `APPROVAL_TOKEN_SECRET` with a unique random value of at least 32 characters. Keep `.env.local` private; it is ignored by Git.

   ```dotenv
   GEMINI_API_KEY=your-key-here
   GEMINI_MODEL=gemini-3.5-flash-lite
   APPROVAL_TOKEN_SECRET=replace-with-a-long-random-secret
   ```

3. Build and launch the services:

   ```powershell
   docker compose up --build
   ```

4. Open the app at **[http://localhost:3000](http://localhost:3000)**.

To stop the services, press `Ctrl+C` in the terminal. If they are running in the background, use `docker compose down` from this directory.

### Local service URLs

| Service | URL |
| --- | --- |
| Web app | [http://localhost:3000](http://localhost:3000) |
| Backend API docs | [http://localhost:8000/docs](http://localhost:8000/docs) |
| Backend liveness | [http://localhost:8000/health](http://localhost:8000/health) |
| Backend readiness | [http://localhost:8000/ready](http://localhost:8000/ready) |
| Mock broker | `http://localhost:8001` |

Readiness checks the backend's dependencies, including PostgreSQL, Redis, the mock broker, and demo quotes. PostgreSQL and Redis are also exposed on ports `5432` and `6379` for local development.

## Try these prompts

```text
Show my portfolio value
Show the TCS price
Give me today's narrative trade report
Buy 10 shares of INFY at market
Buy 10 INFY and 5 TCS shares
If TCS falls below 4000, sell 10 shares
Set my maximum order value to 200000
```

For a trade or rule, inspect the generated proposal and approve or reject it in the interface. The mock broker may simulate a fill or rejection.

## Configuration and operating limits

- `GEMINI_API_KEY` is required for Gemini requests.
- `GEMINI_MODEL` defaults to `gemini-3.5-flash-lite` and can be changed in `.env.local`.
- `APPROVAL_TOKEN_SECRET` must be a private, randomly generated value of at least 32 characters.
- Orders and prices use the local mock broker. The 021 API is **not** configured as a live execution path; setting `USE_REAL_API=true` does not enable live trading.
- Demo quotes and account balances are sample data, not live market information.
- If a broker request times out after submission, its outcome may be unknown. Reconcile it before retrying to avoid duplicate orders.
- Multi-leg mock orders report each leg's status. If a later leg fails after an earlier leg fills, the earlier fill cannot be rolled back.
- The demo does not keep a realized profit/loss ledger, so realized P&L and a maximum daily loss control are not available.

## Development checks

Run these with the relevant services already started:

```powershell
docker compose exec backend python -m unittest discover -s tests -v
docker compose exec mock-api python -m unittest discover -s tests -v
docker compose build frontend
```

## Security note

Never commit `.env.local`, API keys, approval secrets, or other credentials. Start from `.env.example` and provide your own local values. Rotate any credential that has been accidentally exposed.

## Project notes

See [REBUILD_PLAN.md](REBUILD_PLAN.md) for the safety contract, known limitations, and implementation verification stages.
