"""
Orders Router — approve, reject, execute, and fetch orders.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import httpx

from config import settings
from db import get_db
from services.order_service import OrderService
from services.executor import ExecutorService
from services.audit_logger import AuditLogger
from services.instruments import canonical_symbol
from services.risk_engine import RiskBudgetEngine

router = APIRouter()


class ApproveRequest(BaseModel):
    order_id: str


class RejectRequest(BaseModel):
    order_id: str
    reason: str = "Trader rejected"


@router.get("/plans/{plan_id}")
async def get_order_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    plan_result = await db.execute(text("SELECT * FROM order_plans WHERE id = :id"), {"id": plan_id})
    plan = plan_result.mappings().fetchone()
    if not plan:
        raise HTTPException(status_code=404, detail="Order plan not found")
    orders_result = await db.execute(text("SELECT * FROM orders WHERE plan_id = :id ORDER BY created_at, id"), {"id": plan_id})
    return {"plan_id": str(plan_id), "status": plan["status"], "orders": [dict(row) for row in orders_result.mappings()]}


@router.post("/plans/{plan_id}/reject")
async def reject_order_plan(plan_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("UPDATE order_plans SET status='REJECTED' WHERE id=:id AND status='DRAFT' RETURNING id"), {"id": plan_id})
    if not result.fetchone():
        raise HTTPException(status_code=409, detail="Only a pending order plan can be rejected.")
    await db.execute(text("UPDATE orders SET status='REJECTED', rejected_at=NOW() WHERE plan_id=:id AND status='DRAFT'"), {"id": plan_id})
    await AuditLogger(db).log(event_type="ORDER_PLAN_REJECTED", actor="TRADER", payload={"plan_id": plan_id})
    await db.commit()
    return {"success": True, "status": "REJECTED", "message": "The complete plan was rejected; no orders were sent."}


@router.post("/plans/{plan_id}/approve")
async def approve_order_plan(plan_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """One explicit approval for all legs; preflight the complete plan, then submit each leg once."""
    plan_result = await db.execute(text("SELECT * FROM order_plans WHERE id=:id FOR UPDATE"), {"id": plan_id})
    plan = plan_result.mappings().fetchone()
    if not plan:
        raise HTTPException(status_code=404, detail="Order plan not found")
    if plan["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail=f"This plan is already {plan['status'].lower()} and cannot be submitted again.")
    rows_result = await db.execute(text("SELECT * FROM orders WHERE plan_id=:id ORDER BY created_at, id FOR UPDATE"), {"id": plan_id})
    orders = [dict(row) for row in rows_result.mappings()]
    if not 2 <= len(orders) <= 10 or any(row["status"] != "DRAFT" for row in orders):
        raise HTTPException(status_code=409, detail="The plan is incomplete or contains an order that is no longer a draft.")
    if any(row["created_at"] < datetime.now(timezone.utc) - timedelta(seconds=settings.approval_token_ttl_seconds) for row in orders):
        await db.execute(text("UPDATE order_plans SET status='EXPIRED' WHERE id=:id"), {"id": plan_id})
        await db.execute(text("UPDATE orders SET status='EXPIRED' WHERE plan_id=:id AND status='DRAFT'"), {"id": plan_id})
        await db.commit()
        raise HTTPException(status_code=409, detail="The plan expired. Request fresh quotes and review a new plan.")

    # Full-plan preflight: quotes and risk checks all pass before any order is approved/submitted.
    for row in orders:
        raw_quote = await request.app.state.redis.get(f"price:{row['symbol']}")
        try:
            current_quote = float(raw_quote or 0)
        except (TypeError, ValueError):
            current_quote = 0
        if current_quote <= 0:
            raise HTTPException(status_code=409, detail=f"No current quote for {row['symbol']}; no plan orders were submitted.")
        quoted_price = float(row["quoted_price"] or row["price"] or 0)
        if quoted_price <= 0 or abs(current_quote - quoted_price) / quoted_price * 100 > 0.5:
            raise HTTPException(status_code=409, detail=f"{row['symbol']} moved more than 0.5% since review; no plan orders were submitted. Request a fresh plan.")
        risk_draft = {"symbol": row["symbol"], "side": row["side"], "order_type": row["order_type"],
                      "quantity": row["quantity"], "price": row["price"], "trigger_price": row["trigger_price"],
                      "quoted_price": current_quote}
        risk = await RiskBudgetEngine(db).check_order(risk_draft)
        if not risk.passed:
            raise HTTPException(status_code=422, detail=f"Plan blocked for {row['symbol']}: {risk.reason}. No plan orders were submitted.")

    # Claim the whole plan before any broker request to prevent duplicate clicks/retries.
    claimed = await db.execute(text("UPDATE order_plans SET status='EXECUTING', approved_at=NOW() WHERE id=:id AND status='DRAFT' RETURNING id"), {"id": plan_id})
    if not claimed.fetchone():
        raise HTTPException(status_code=409, detail="The plan was already claimed for approval.")
    await AuditLogger(db).log(event_type="ORDER_PLAN_APPROVED", actor="TRADER", payload={"plan_id": plan_id, "order_ids": [str(r['id']) for r in orders]})
    await db.commit()

    results = []
    executor = ExecutorService(db)
    order_service = OrderService(db)
    for row in orders:
        try:
            approval = await order_service.approve(str(row["id"]))
            outcome = await executor.execute(str(row["id"]), approval["token"])
            results.append({"order_id": str(row["id"]), "symbol": row["symbol"], "side": row["side"],
                            "status": outcome.status, "success": outcome.success, "message": outcome.message,
                            "filled_quantity": outcome.filled_quantity, "average_price": outcome.average_price})
            if outcome.status not in {"FILLED", "PARTIAL"}:
                break
        except Exception as exc:
            results.append({"order_id": str(row["id"]), "symbol": row["symbol"], "status": "NOT_SUBMITTED", "success": False,
                            "message": "A later plan leg was not submitted after an earlier leg failed. Check order status before any new request."})
            break
    finished = len(results) == len(orders) and all(item["status"] == "FILLED" for item in results)
    uncertain = any(item["status"] == "SUBMITTED" for item in results)
    final_status = "COMPLETED" if finished else ("SUBMITTED" if uncertain else ("PARTIAL" if results else "FAILED"))
    await db.execute(text("UPDATE order_plans SET status=:status, completed_at=NOW() WHERE id=:id"), {"status": final_status, "id": plan_id})
    await AuditLogger(db).log(event_type="ORDER_PLAN_FINISHED", actor="SYSTEM", payload={"plan_id": plan_id, "status": final_status, "results": results})
    await db.commit()
    return {"success": final_status == "COMPLETED", "plan_id": plan_id, "status": final_status, "results": results,
            "message": "All plan legs filled." if finished else "Plan processing stopped. Review each leg status; uncertain submissions must be reconciled, never retried."}


class ModifyDraftRequest(BaseModel):
    symbol: str
    side: str
    order_type: str
    quantity: int = Field(gt=0, le=10_000)
    price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    trigger_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return canonical_symbol(value)

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("Order side must be BUY or SELL.")
        return normalized

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"MARKET", "LIMIT", "SL", "SL-M"}:
            raise ValueError("Order type must be MARKET, LIMIT, SL, or SL-M.")
        return normalized

    @model_validator(mode="after")
    def validate_prices(self):
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("A LIMIT order requires a positive limit price.")
        if self.order_type in {"SL", "SL-M"} and self.trigger_price is None:
            raise ValueError("A stop order requires a positive trigger price.")
        if self.order_type != "LIMIT" and self.price is not None:
            raise ValueError("Only LIMIT orders can include a limit price.")
        if self.order_type not in {"SL", "SL-M"} and self.trigger_price is not None:
            raise ValueError("Only stop orders can include a trigger price.")
        return self


@router.post("/approve")
async def approve_order(req: ApproveRequest, db: AsyncSession = Depends(get_db)):
    """
    Trader approves a draft order.
    Generates a hash-bound token and immediately executes via the Executor.
    """
    order_service = OrderService(db)
    executor = ExecutorService(db)
    audit = AuditLogger(db)

    try:
        # Generate token + mark APPROVED
        approval = await order_service.approve(req.order_id)

        await audit.log(
            event_type="ORDER_APPROVED",
            order_id=req.order_id,
            actor="TRADER",
            payload={"token_expires_at": approval["expires_at"]},
        )

        # Execute immediately
        result = await executor.execute(req.order_id, approval["token"])

        await audit.log(
            event_type="ORDER_SUBMITTED",
            order_id=req.order_id,
            actor="SYSTEM",
            payload={
                "status": result.status,
                "filled_quantity": result.filled_quantity,
                "average_price": result.average_price,
            },
        )

        return {
            "success": result.success,
            "status": result.status,
            "exchange_order_id": result.exchange_order_id,
            "filled_quantity": result.filled_quantity,
            "average_price": result.average_price,
            "message": result.message,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/reject")
async def reject_order(req: RejectRequest, db: AsyncSession = Depends(get_db)):
    """Trader rejects a draft — draft is discarded, no order placed."""
    order_service = OrderService(db)
    audit = AuditLogger(db)

    try:
        await order_service.reject(req.order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await audit.log(
        event_type="ORDER_REJECTED",
        order_id=req.order_id,
        actor="TRADER",
        payload={"reason": req.reason},
    )
    await db.commit()

    return {"success": True, "message": "Order draft rejected and discarded."}


@router.get("/{order_id}")
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    order_service = OrderService(db)
    order = await order_service.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.put("/{order_id}")
async def modify_order_draft(order_id: str, req: ModifyDraftRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Update an unapproved draft, refreshing its quote and rerunning risk checks."""
    current_result = await db.execute(
        text("SELECT * FROM orders WHERE id = :id FOR UPDATE"),
        {"id": order_id},
    )
    current = current_result.mappings().fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="Order draft not found")
    if current["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail="Only an unapproved draft can be modified.")

    try:
        quote_value = await request.app.state.redis.get(f"price:{req.symbol}")
        quoted_price = float(quote_value) if quote_value else 0
        if quoted_price <= 0:
            raise ValueError("A fresh quote is unavailable for this symbol.")
    except (TypeError, ValueError) as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc) or "A fresh quote is unavailable for this symbol.") from None
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=503, detail="The quote service is temporarily unavailable; the draft was not changed.") from None

    draft_data = {
        "symbol": req.symbol,
        "side": req.side,
        "order_type": req.order_type,
        "quantity": req.quantity,
        "price": req.price,
        "trigger_price": req.trigger_price,
        "quoted_price": quoted_price,
    }
    risk = await RiskBudgetEngine(db).check_order(draft_data)
    if not risk.passed:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"Draft update rejected by risk checks: {risk.reason}")

    updated = await db.execute(
        text("""UPDATE orders SET
                symbol = :symbol, side = :side, order_type = :order_type,
                quantity = :quantity, price = :price, trigger_price = :trigger_price,
                quoted_price = :quoted_price, risk_score = :risk_score,
                risk_check_passed = TRUE, approval_token = NULL,
                token_expires_at = NULL, approved_at = NULL,
                raw_user_message = 'Draft modified by trader', updated_at = NOW()
            WHERE id = :id AND status = 'DRAFT'
                AND created_at >= NOW() - (:draft_ttl * INTERVAL '1 second')
            RETURNING id"""),
        {**draft_data, "risk_score": risk.score, "id": order_id, "draft_ttl": settings.approval_token_ttl_seconds},
    )
    if not updated.fetchone():
        await db.rollback()
        raise HTTPException(status_code=409, detail="The draft changed while it was being updated. Refresh and try again.")

    await AuditLogger(db).log(
        event_type="DRAFT_UPDATED",
        order_id=order_id,
        actor="TRADER",
        payload={
            "before": {
                key: float(current[key]) if isinstance(current[key], Decimal) else current[key]
                for key in ("symbol", "side", "order_type", "quantity", "price", "trigger_price", "quoted_price")
            },
            "after": {**draft_data, "risk_score": risk.score},
        },
    )
    await db.commit()
    return {
        "success": True,
        "order_id": order_id,
        "status": "DRAFT",
        "draft": {**draft_data, "risk_score": risk.score, "risk_check_passed": True},
        "message": "Draft updated with a fresh quote and risk checks. Review it again before approval.",
    }


@router.delete("/{order_id}")
async def cancel_order_draft(order_id: str, db: AsyncSession = Depends(get_db)):
    """Cancel an unapproved draft without submitting it to the broker."""
    result = await db.execute(
        text("UPDATE orders SET status = 'CANCELLED', updated_at = NOW() WHERE id = :id AND status = 'DRAFT' RETURNING id"),
        {"id": order_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=409, detail="Only an unapproved draft can be cancelled.")
    await AuditLogger(db).log(
        event_type="DRAFT_CANCELLED",
        order_id=order_id,
        actor="TRADER",
        payload={"reason": "Trader cancelled draft"},
    )
    await db.commit()
    return {"success": True, "message": "Draft cancelled; no broker order was submitted."}


@router.post("/{order_id}/reconcile")
async def reconcile_order(order_id: str, db: AsyncSession = Depends(get_db)):
    """Read the broker order book for an order whose submission outcome is unknown."""
    result = await ExecutorService(db).reconcile(order_id)
    return {
        "success": result.success,
        "status": result.status,
        "exchange_order_id": result.exchange_order_id,
        "filled_quantity": result.filled_quantity,
        "average_price": result.average_price,
        "message": result.message,
    }


@router.get("/")
async def list_orders(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
    )
    return {"orders": [dict(r) for r in result.mappings()]}
