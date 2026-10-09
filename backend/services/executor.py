"""
Executor Service — the ONLY component that can submit orders to the broker.

Critical rules:
1. No LLM involvement here. Pure deterministic logic.
2. Validates the approval token before touching the broker.
3. Checks price drift — if price moved beyond tolerance since the quote, re-quotes.
4. Uses client_order_id for idempotency — safe to retry.
5. Checks order book before any retry to avoid duplicates.
"""

from dataclasses import dataclass
import hmac
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services.approval_token import ApprovalTokenService, TokenResult
from services.audit_logger import AuditLogger


PRICE_DRIFT_TOLERANCE_PCT = 0.5   # 0.5% — if price moved more, re-quote before submitting


@dataclass
class ExecutionResult:
    success: bool
    status: str           # FILLED | PARTIAL | REJECTED | FAILED | PRICE_DRIFTED
    exchange_order_id: Optional[str] = None
    filled_quantity: int = 0
    average_price: Optional[float] = None
    message: str = ""


class ExecutorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.token_service = ApprovalTokenService()
        self.broker_url = settings.mock_api_url

    async def execute(self, order_id: str, token: str) -> ExecutionResult:
        """
        Execute an approved order.

        Steps:
        1. Load order from DB
        2. Validate token against order
        3. Check price drift — if too much, fail with PRICE_DRIFTED (frontend will re-quote)
        4. Submit to broker with client_order_id for idempotency
        5. Update order status in DB
        """
        # --- Load order ---
        result = await self.db.execute(
            text("SELECT * FROM orders WHERE id = :id"),
            {"id": order_id},
        )
        order = result.mappings().fetchone()

        if not order:
            return ExecutionResult(success=False, status="FAILED", message="Order not found")

        if order["status"] != "APPROVED":
            return ExecutionResult(
                success=False,
                status="FAILED",
                message=f"Order is in status '{order['status']}', not APPROVED",
            )

        # --- Validate token ---
        if not order.get("approval_token") or not hmac.compare_digest(
            str(token), str(order["approval_token"])
        ):
            token_result = TokenResult(
                valid=False,
                reason="Approval token is not the active token stored for this order",
            )
        else:
            token_result = self.token_service.validate(token, dict(order))
        if not token_result.valid:
            # Log token rejection to audit
            await self.db.execute(
                text(
                    "INSERT INTO audit_log (event_type, order_id, actor, payload) "
                    "VALUES ('TOKEN_REJECTED', :oid, 'SYSTEM', CAST(:payload AS jsonb))"
                ),
                {"oid": order_id, "payload": f'{{"reason": "{token_result.reason}"}}'},
            )
            await self.db.commit()
            return ExecutionResult(
                success=False,
                status="FAILED",
                message=f"Token validation failed: {token_result.reason}",
            )

        # --- Check price drift for limit/market orders ---
        async with httpx.AsyncClient(timeout=10.0) as http:
            try:
                quote_resp = await http.get(f"{self.broker_url}/quote/{order['symbol']}")
                quote_resp.raise_for_status()
                current_price = float(quote_resp.json().get("ltp") or 0)
                if current_price <= 0:
                    raise ValueError("Quote response did not contain a positive last traded price")
            except (httpx.HTTPError, ValueError, TypeError):
                await self.db.execute(
                    text("""UPDATE orders SET status = 'DRAFT', approval_token = NULL,
                        token_expires_at = NULL, approved_at = NULL WHERE id = :id AND status = 'APPROVED'"""),
                    {"id": order_id},
                )
                await self.db.commit()
                return ExecutionResult(
                    success=False,
                    status="PRICE_DRIFTED",
                    message="A current quote is unavailable. No order was sent; create a fresh draft and review its quote.",
                )

        if order.get("quoted_price"):
            drift_pct = abs(current_price - float(order["quoted_price"])) / float(order["quoted_price"]) * 100
            if drift_pct > PRICE_DRIFT_TOLERANCE_PCT:
                await self.db.execute(
                    text(
                        "UPDATE orders SET status = 'DRAFT', approval_token = NULL, token_expires_at = NULL, approved_at = NULL WHERE id = :id AND status = 'APPROVED'"
                    ),
                    {"id": order_id},
                )
                await self.db.commit()
                return ExecutionResult(
                    success=False,
                    status="PRICE_DRIFTED",
                    message=(
                        f"Price moved by {drift_pct:.2f}% since you approved "
                        f"(was ₹{order['quoted_price']:.2f}, now ₹{current_price:.2f}). "
                        f"Please review the updated confirmation card."
                    ),
                )

        # Claim before making a network request. This serializes double-clicks and
        # concurrent approvals. An uncertain outcome stays SUBMITTED.
        claim = await self.db.execute(
            text("""UPDATE orders SET status = 'SUBMITTED', submitted_at = NOW()
                WHERE id = :id AND status = 'APPROVED' RETURNING id"""),
            {"id": order_id},
        )
        if not claim.fetchone():
            await self.db.rollback()
            return ExecutionResult(
                success=False,
                status="FAILED",
                message="This order has already been claimed for execution or is no longer approved.",
            )
        await self.db.commit()

        # --- Submit once to broker with its idempotency key ---
        async with httpx.AsyncClient(timeout=15.0) as http:
            try:
                broker_resp = await http.post(
                    f"{self.broker_url}/orders",
                    json={
                        "client_order_id": order["client_order_id"],
                        "symbol":       order["symbol"],
                        "side":         order["side"],
                        "order_type":   order["order_type"],
                        "quantity":     order["quantity"],
                        "price":        order["price"],
                        "trigger_price": order["trigger_price"],
                    },
                )
                broker_resp.raise_for_status()
                broker_data = broker_resp.json()
                if not isinstance(broker_data, dict) or not broker_data.get("status"):
                    raise ValueError("Broker response is missing an order status")
                if broker_data["status"] == "PROCESSING":
                    return ExecutionResult(
                        success=False,
                        status="SUBMITTED",
                        message="The broker still reports this order as processing. Reconcile its client order ID before taking further action.",
                    )
                if broker_data["status"] not in {"FILLED", "PARTIAL", "REJECTED", "CANCELLED", "FAILED"}:
                    raise ValueError("Broker returned an unsupported order status")

            except (httpx.HTTPError, ValueError) as e:
                # Network failure — do NOT retry automatically. Let trader decide.
                return ExecutionResult(
                    success=False,
                    status="SUBMITTED",
                    message=f"Execution outcome is unknown ({str(e)}). Do not retry; reconcile this client order ID with the broker first.",
                )

        exec_status = broker_data.get("status", "FAILED")
        filled_qty = broker_data.get("filled_quantity", 0)
        avg_price = broker_data.get("average_price")
        exchange_id = broker_data.get("exchange_order_id")

        # --- Update order in DB ---
        await self.db.execute(
            text("""
                UPDATE orders SET
                    status = :status,
                    filled_quantity = :filled_qty,
                    average_price = :avg_price,
                    exchange_order_id = :exchange_id,
                    submitted_at = NOW(),
                    filled_at = CASE WHEN :is_filled THEN NOW() ELSE NULL END
                WHERE id = :id
            """),
            {
                "id": order_id,
                "status": exec_status,
                "filled_qty": filled_qty,
                "avg_price": avg_price,
                "exchange_id": exchange_id,
                "is_filled": exec_status in ("FILLED", "PARTIAL"),
            },
        )

        # --- Audit log ---
        await self.db.execute(
            text(
                "INSERT INTO audit_log (event_type, order_id, actor, payload) "
                "VALUES ('ORDER_EXECUTED', :oid, 'SYSTEM', CAST(:payload AS jsonb))"
            ),
            {
                "oid": order_id,
                "payload": f'{{"status": "{exec_status}", "filled_qty": {filled_qty}, "avg_price": {avg_price or 0}}}',
            },
        )
        await self.db.commit()

        return ExecutionResult(
            success=exec_status in ("FILLED", "PARTIAL"),
            status=exec_status,
            exchange_order_id=exchange_id,
            filled_quantity=filled_qty,
            average_price=avg_price,
            message=broker_data.get("reject_reason", ""),
        )

    async def reconcile(self, order_id: str) -> ExecutionResult:
        """Check the broker's order book after a request with an uncertain outcome."""
        result = await self.db.execute(
            text("SELECT * FROM orders WHERE id = :id"),
            {"id": order_id},
        )
        order = result.mappings().fetchone()
        if not order:
            return ExecutionResult(success=False, status="FAILED", message="Order not found")
        if order["status"] != "SUBMITTED":
            return ExecutionResult(
                success=False,
                status=order["status"],
                message=f"Only an order with an uncertain SUBMITTED status needs reconciliation; current status is {order['status']}.",
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as http:
                response = await http.get(
                    f"{self.broker_url}/orders/by-client-id/{order['client_order_id']}"
                )
                if response.status_code == 404:
                    return ExecutionResult(
                        success=False,
                        status="SUBMITTED",
                        message="The broker has not confirmed this order. It remains blocked from retry; check again before creating a new draft.",
                    )
                response.raise_for_status()
                broker_order = response.json()
        except httpx.HTTPError as exc:
            return ExecutionResult(
                success=False,
                status="SUBMITTED",
                message=f"Could not reconcile with the broker ({exc}). The order remains blocked from retry.",
            )

        if broker_order.get("client_order_id") != order["client_order_id"]:
            return ExecutionResult(
                success=False,
                status="SUBMITTED",
                message="The broker response did not match this client order ID. The order remains blocked from retry.",
            )
        broker_status = broker_order.get("status")
        if broker_status == "PROCESSING":
            return ExecutionResult(
                success=False,
                status="SUBMITTED",
                message="The broker still reports this order as processing. Check again later; do not retry it.",
            )
        if broker_status not in {"FILLED", "PARTIAL", "REJECTED", "CANCELLED", "FAILED"}:
            return ExecutionResult(
                success=False,
                status="SUBMITTED",
                message="The broker returned an unknown status. The order remains blocked from retry.",
            )

        await self.db.execute(
            text("""UPDATE orders SET status = :status, filled_quantity = :filled_qty,
                average_price = :avg_price, exchange_order_id = :exchange_id,
                filled_at = CASE WHEN :is_filled THEN NOW() ELSE NULL END
                WHERE id = :id AND status = 'SUBMITTED'"""),
            {
                "id": order_id,
                "status": broker_status,
                "filled_qty": broker_order.get("filled_quantity", 0),
                "avg_price": broker_order.get("average_price"),
                "exchange_id": broker_order.get("exchange_order_id"),
                "is_filled": broker_status in {"FILLED", "PARTIAL"},
            },
        )
        await AuditLogger(self.db).log(
            event_type="ORDER_RECONCILED",
            order_id=order_id,
            actor="SYSTEM",
            payload={"client_order_id": order["client_order_id"], "status": broker_status},
        )
        await self.db.commit()
        return ExecutionResult(
            success=broker_status in {"FILLED", "PARTIAL"},
            status=broker_status,
            exchange_order_id=broker_order.get("exchange_order_id"),
            filled_quantity=broker_order.get("filled_quantity", 0),
            average_price=broker_order.get("average_price"),
            message=broker_order.get("reject_reason", "Order status reconciled with the broker."),
        )
