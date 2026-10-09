# StockItUp Rebuild Plan

## Product contract

StockItUp is a chat interface over a deterministic trading workflow. Gemini may interpret a request and propose typed actions, but it never submits an order. A draft is validated against supported instruments, a fresh quote, and risk limits. The user sees the complete order and quote, then explicitly approves or rejects it. Only the backend executor can submit an approved order. The default broker is the local mock API; enabling a live broker requires a separately verified integration and explicit configuration.

## Decisions

- Keep the connected Gemini provider and model configurable through environment variables.
- Keep simulated trading as the default; never silently fall back between mock and real brokers.
- Keep order execution separate from model tools and frontend code.
- Bind approval to the order identity and all material order fields, including quote and limit/trigger prices; expire and consume it once.
- Make retries idempotent and reconcile uncertain submissions before any retry.
- Persist standing rules only after explicit confirmation. Reload them after restart, fire each at most once, and pause with an audit event when their quote is stale.
- Show actionable, sanitized errors in the UI and preserve detailed server-side diagnostics.
- Do not claim live market data or live broker support unless the configured provider is actually active and its health is known.

## Rebuild stages and completion checks

1. **Baseline and contracts** — document actual services and configuration; define validated request/response schemas and instrument handling. Reject malformed, unsupported, or ambiguous trade requests before creating drafts.
2. **Read-only copilot** — make portfolio, position, and quote answers deterministic and traceable to data sources. Gemini may explain results but must not invent account facts.
3. **Order lifecycle** — create a fresh-quote draft; show the exact symbol, side, quantity, order type, limit/trigger price, quote timestamp, estimated amount, and risk result. Explicit approval executes only that immutable draft; reject/expiry/price drift are clear terminal or redraft states.
4. **Execution reliability** — enforce unique client order IDs, single-use signed approvals, broker reconciliation after timeouts, and safe repeat requests. Never report success from an ambiguous network response.
5. **Standing instructions** — validate and preview rules; explicit activation; durable scheduling/recovery; freshness and risk checks; one-fire semantics; pause/cancel controls and audit history.
6. **Operations and UI** — health/readiness for each dependency, consistent error envelopes, visible mock/live mode, audit views, and restart-safe state.
7. **Verification** — exercise valid/invalid requests, prompt injection, price movement, stale quotes, double-clicks, network timeouts, restarts, rule replays, and database failure. The safety acceptance condition is zero broker submissions without the exact required approval and zero duplicate submissions for one client order ID.

## Current baseline findings and progress

- The app currently routes execution to the mock API even though settings expose a real API toggle; the real adapter is not yet an integrated execution path.
- Gemini is configured in the backend, but earlier failures came from SDK tool-call compatibility, SQL parameter casting, and frontend/database lifecycle mismatches.
- Standing instructions are now validated against supported symbols and implemented trigger types, audited on activation/expiry/stale data, started after the first price snapshot, and routed through risk checks and the shared executor.
- The UI and API include fixes for quote display, tool-call persistence, approval-token storage width, standing-rule confirmation cards, database JSON casts, duplicate-approval prevention, and mock/demo labeling.
- README and UI status text now describe the current mock mode and explicitly state that live 021 execution is not integrated.

### Implemented in this rebuild pass

- Gemini read-only portfolio requests use the same mock-broker data as the sidebar instead of stale hard-coded answers.
- Gemini tool-call round trips preserve the complete model turn (including thought signatures) and function-call IDs; invalid tool inputs are rejected before draft creation. Provider and broker failures are logged server-side and returned to the UI as sanitized SSE errors.
- The mock mode has a stable approval-token secret in `.env.local`; a process-local safe default keeps a fresh demo bootable.
- Order approvals bind to symbol, side, type, quantity, limit/trigger prices, and quote; conditional database transitions prevent concurrent approvals, expired drafts, and repeated submissions.
- Missing quotes and price drift stop execution; uncertain broker responses remain `SUBMITTED` and are never blindly retried.
- The mock broker stores idempotency intents and results in persistent Redis, binds each client order ID to the full order intent, and rejects key reuse with changed fields; the UI can reconcile an uncertain submission by client order ID.
- Standing-rule execution now uses a deterministic client order ID, links its order before approval, resumes interrupted DRAFT/APPROVED states after restart, and reconciles SUBMITTED orders instead of resending them.
- Rules pause on missing/stale quotes, risk rejection, or price drift. Traders can resume a paused rule only before it has fired and while a fresh quote exists; active or safely paused rules can be cancelled and these actions are audited.
- The mock broker's unused 021 login/data/execution branches are removed. It refuses to start if a legacy live flag is enabled, preventing accidental silent fallback to demo data.
- Added 50 backend tests for Gemini tool round-trip compatibility, tool validation, sanitized provider errors, audit serialization, approval expiry/tampering, simulated fill persistence, broker-call suppression for invalid approval or quote drift, concurrent duplicate-submit suppression, instrument allowlisting, standing-rule trigger-once and recovery lifecycle, deterministic IDs, first-snapshot mock quotes, dependency/stale-quote readiness, risk-limit lifecycle, draft edit/cancel validation, and report-tool wiring; added 8 mock API tests for idempotent client-order IDs, changed-intent rejection, filled/rejected portfolio projections, daily report accuracy, instrument validation, fallback quote behavior, and fail-closed live-mode configuration.
- Verified a labeled audit event persisted through a PostgreSQL restart and was readable through `/audit/`; verified Redis AOF retained a temporary sentinel after restart. Both markers were removed after the check, and all containers returned healthy.
- Verified Gemini read-only quote and portfolio responses, order draft creation with a displayed quote/value, rejection and audit history, backend readiness, mock quote retrieval, and a production frontend build.
- After the approval fix, verified the complete browser mock path: Gemini drafted a quoted one-share order, approval returned `FILLED`, the chat displayed the final fill result, the portfolio refreshed to reflect the fill, and the audit log retained the lifecycle events.
- Reproduced the approval-path failure: PostgreSQL rejected the fill update because `:status` was reused with conflicting type inference. Replaced the repeated status comparison with a boolean `:is_filled` parameter in both execution and reconciliation updates; added a passing simulated fill persistence test.
- The one-share mock order whose approval response had failed was safely reconciled by client order ID; the mock broker confirmed FILLED and the audit log recorded `ORDER_RECONCILED`. This avoided any retry or duplicate submission.
- Filled mock orders are now applied to account cash and positions from durable Redis order history; rejected/zero-fill orders leave the portfolio unchanged. The sidebar reflects these account changes through its existing refresh cycle. Approval/rejection outcomes remain visible in the chat after the card closes.
- Rebuilt/restarted backend and frontend after the fix. The browser still displays MOCK MODE; the instruction screen renders without standing rules. Backend, frontend, mock API, PostgreSQL, and Redis are running; database and Redis report healthy.
- Removed the Yahoo Finance dependency from the mock-mode price-polling path after runtime logs showed repeated failures and delayed snapshots. Mock quotes are fetched concurrently from the local mock broker, labeled `fixed_demo_fallback`, and immediately populate Redis on startup. Verified the fresh six-symbol snapshot in Redis after a backend restart.
- Rechecked after restart: a Gemini read-only portfolio request returned a response, the active TCS standing rule remained listed, and the previously triggered INFY rule remained in PostgreSQL with `FILLED` status plus matching audit records. The refreshed UI now clarifies that an explicitly activated standing rule authorizes its future trigger.
- Added `/ready` to check PostgreSQL, Redis, the mock broker, and a fresh quote snapshot; the existing `/health` remains a liveness check. Docker healthchecks gate backend and frontend startup on dependency readiness. Runtime returned all four checks as `ok`, and unit tests cover healthy, stale/malformed quote, database outage, and Redis outage cases.
- Risk limits can now be proposed through Gemini and applied only after explicit approval; proposals persist with expiry, stale-value protection, idempotent approval, and audit events. Editable limits are bounded to maximum order value, shares per order, and orders per day. Maximum daily loss is deliberately unavailable until the demo has an auditable realized-P&L ledger. The current backend suite passes 50 tests, the mock API suite passes 8 tests, and the frontend production build succeeds with the existing UI restored.
- Added a deterministic daily trade-report endpoint and Gemini read tool. It summarizes the day’s recorded demo orders, fills, shares, turnover, and pending/rejected/cancelled counts. It explicitly reports realized P&L as unavailable instead of estimating it from incomplete history. The live browser smoke test returned the same counts and turnover as the mock broker endpoint.
- Unapproved order drafts can be edited through the API only while still DRAFT and within the approval window. Edits require a fresh quote and a passing risk check, replace the reviewed fields, and are audited; draft cancellation is conditional and audited. These backend paths are covered by tests; the current UI does not yet expose them.
- Multi-order requests now use one persisted order plan and one approve/reject action. Approval locks and preflights every leg for plan state, expiry, fresh quote/drift, and risk before claiming execution; a plan cannot be replayed. Per-leg results are recorded and the runner stops after a failure or uncertain submission. Added backend coverage for whole-plan success and all-plan quote-drift rejection.
- The order-plan card is integrated into the existing chat UI. Database startup creates the order-plan table and link column for both new and existing local databases.
- Fixed paused standing rules so their configured expiry still takes effect when they have not yet triggered; the regression test confirms expiry is audited.

### Remaining work

- Exercise newly created standing-rule trigger and cancellation transitions in an isolated database state, including restart boundaries between each persisted lifecycle transition. Existing persisted rules and their stale-pause/resume/cancel/trigger audit events are confirmed in the current demo database.
- Add a full mock integration scenario for a newly created standing rule, its single trigger, cancellation/terminal states, and restart recovery; current runtime evidence is from the existing demo rules and audit records.
- Extend coverage for broker rejection and concurrent/double-click approval against PostgreSQL, and run outage recovery scenarios with live containers. Unit tests already cover expired/tampered approvals, quote drift, wrong tokens, Gemini/provider error sanitization, mock idempotency, database/Redis readiness failures, and reconciliation instead of resubmission.
- The proposal's draft modification/cancellation UX and second-approver flow remain unimplemented. The demo has no authenticated user/approver identities, so it cannot yet establish that two distinct people approved a risky order. Maximum daily loss is also not configurable because there is no realized-P&L ledger to enforce it safely.
- Verify browser states for approval expiry, price drift, rejected mock fills, and unknown submission reconciliation. The successful approval and read-only Gemini flows, standing-rule create/trigger/stale-pause/resume/cancel audit events, and mock-mode UI have been exercised.
- Integrate live 021 only after the official API contract and sandbox credentials are available; it is not enabled by this rebuild pass.

Latest verification after grouped plans: 54 backend tests pass, 8 mock API tests pass, frontend production build succeeds, plan endpoints are present in OpenAPI, and `/ready` reports PostgreSQL, Redis, mock broker, and demo quotes healthy.

## Limits

This plan cannot guarantee that external APIs, networks, exchanges, or market data providers never fail. It makes failures explicit, prevents unsafe automatic retries, and verifies the local mock workflow. Live 021 trading remains out of scope until its official contract and sandbox credentials can be verified.
