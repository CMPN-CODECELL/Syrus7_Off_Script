# StockItUp — AI Trading Copilot

StockItUp is a demo trading copilot built with Next.js, FastAPI, Gemini, PostgreSQL, Redis, and a local mock broker.

## Current operating mode

- Gemini interprets requests and can call read-only broker tools. It can create order and standing-instruction drafts, but cannot submit orders itself.
- The app currently routes orders to the local mock broker and uses a demo portfolio. Quotes come from fixed mock-broker demo prices and are not live market data.
- A user must explicitly approve each order draft. Multi-order requests can be presented as one persisted plan with a single approve/reject action after full-plan quote and risk preflight. Standing instructions also require explicit activation.
- The 021 API is not an integrated live execution path. Do not set `USE_REAL_API=true` expecting live trading.

## Start locally

Requirements: Docker Desktop with Compose, and a Gemini API key.

1. Copy `.env.example` to `.env.local`.
2. Set `GEMINI_API_KEY` and replace `APPROVAL_TOKEN_SECRET` with a unique random value of at least 32 characters. Keep `.env.local` private; do not commit it.
3. Run `docker compose up --build`.
4. Open <http://localhost:3000>. Backend docs are at <http://localhost:8000/docs>. `/health` checks backend liveness; `/ready` checks PostgreSQL, Redis, the mock broker, and fresh demo quotes.

Services: frontend `3000`, backend `8000`, mock broker `8001`, PostgreSQL `5432`, Redis `6379`.

## Try it

- `Show my portfolio value`
- `Show the TCS price`
- `Give me today's narrative trade report` â€” summarizes recorded demo activity. Realized P&L is shown as unavailable because this demo does not maintain a realized-P&L ledger.
- `Buy 10 shares of INFY at market` — inspect the quote and details, then approve or reject the draft.
- `Buy 10 INFY and 5 TCS shares` — review one grouped plan and approve or reject every leg together.
- `If TCS falls below 4000, sell 10 shares` — inspect the proposed rule, then activate or reject it.

The mock broker can return simulated fills or rejections. A network timeout after submitting an order is treated as an unknown outcome and must be reconciled before any retry. Multi-leg broker orders cannot be rolled back if a later leg fails after an earlier one fills; the plan reports per-leg statuses and stops submitting subsequent legs after a failure.

## Risk budgets

Try `Set my maximum order value to 200000`, review the current and proposed values, then approve or reject the proposal. Supported editable limits are maximum order value, maximum shares per order, and maximum orders per day; each has a hard demo ceiling. Maximum daily loss is not offered because this demo does not keep a realized-profit/loss ledger to enforce it reliably.

## Configuration

`GEMINI_MODEL` defaults to `gemini-3.5-flash-lite` and can be changed in `.env.local`. `GEMINI_API_KEY` and `APPROVAL_TOKEN_SECRET` are required for normal operation. Never place credentials in source code or commit them.

## Architecture

- `frontend/`: Next.js chat, approval cards, portfolio display, instructions, and audit history.
- `backend/`: FastAPI, Gemini function calling, request validation, risk checks, approval tokens, execution, and standing-instruction runner.
- `mock-api/`: local demo portfolio, quotes, instrument list, and simulated orders.
- `db/migrations/`: PostgreSQL schema migrations.

See [REBUILD_PLAN.md](REBUILD_PLAN.md) for the safety contract, known limits, and verification stages. This project cannot guarantee external APIs or networks will never fail; it is designed to stop safely and make uncertain outcomes visible.

## Verification

Run the backend unit suite with `docker compose exec backend python -m unittest discover -s tests -v` and the mock-broker suite with `docker compose exec mock-api python -m unittest discover -s tests -v`. Build the frontend with `docker compose build frontend`.
