"""
Chat Router — SSE streaming endpoint for the LLM agent.
Handles message submission and streams the agent's response back to the frontend.
"""
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from agent.agent import TradingAgent
from db import get_db
from services.audit_logger import AuditLogger
from services.injection_shield import InjectionShield
from services.risk_engine import RiskBudgetEngine
from services.order_service import OrderService

router = APIRouter()
logger = logging.getLogger(__name__)
agent = TradingAgent()
injection_shield = InjectionShield()


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[dict] = []  # [{role, content}, ...]
    session_id: Optional[str] = None


@router.post("/stream")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    SSE endpoint: receives a user message, runs it through the agent,
    streams back the response token by token.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # 1. Injection shield — check user message before sending to LLM
    shield_result = injection_shield.check(req.message)

    async def generate():
        if shield_result.flagged:
            # Blocked — tell the user without executing anything
            yield f"data: {json.dumps({'type': 'injection_blocked', 'reason': shield_result.reason})}\n\n"
            yield f"data: {json.dumps({'type': 'text', 'content': f'⚠️ I detected potentially adversarial content in your message and blocked it for safety. Reason: {shield_result.reason}'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # Build message history for Gemini
        messages = list(req.conversation_history)
        messages.append({"role": "user", "content": req.message})

        order_service = OrderService(db)
        risk_engine = RiskBudgetEngine(db)
        audit = AuditLogger(db)

        async def on_draft(tool_name: str, draft_data: dict):
            """Called by agent when it creates a draft. We validate and save to DB."""
            if tool_name == "create_order_plan":
                legs = draft_data.get("orders", [])
                if not 2 <= len(legs) <= 10:
                    raise ValueError("An order plan must contain between 2 and 10 orders.")
                checked = []
                for leg in legs:
                    risk_result = await risk_engine.check_order(leg)
                    if not risk_result.passed:
                        raise ValueError(f"Plan blocked: {leg['symbol']} failed risk checks: {risk_result.reason}")
                    leg["risk_score"] = risk_result.score
                    leg["risk_check_passed"] = True
                    checked.append(leg)
                plan_id = str(uuid.uuid4())
                await db.execute(text("INSERT INTO order_plans (id, raw_user_message) VALUES (:id, :message)"),
                                 {"id": plan_id, "message": req.message})
                for leg in checked:
                    order = await order_service.create_draft(req.message, leg, plan_id=plan_id)
                    leg["order_id"] = str(order.id)
                    leg["client_order_id"] = order.client_order_id
                draft_data["plan_id"] = plan_id
                draft_data["orders"] = checked
                await audit.log(event_type="ORDER_PLAN_CREATED", actor="LLM", payload=draft_data)
                await db.commit()
            elif tool_name == "create_order_draft":
                # Risk check
                risk_result = await risk_engine.check_order(draft_data)
                draft_data["risk_score"] = risk_result.score
                draft_data["risk_check_passed"] = risk_result.passed
                draft_data["risk_reason"] = risk_result.reason

                # Save draft to DB and get an order ID
                order = await order_service.create_draft(
                    raw_message=req.message,
                    draft_data=draft_data,
                )
                draft_data["order_id"] = str(order.id)
                draft_data["client_order_id"] = order.client_order_id

                await audit.log(
                    event_type="DRAFT_CREATED",
                    order_id=order.id,
                    payload=draft_data,
                )
                # Commit before emitting the draft so approval can load the new row.
                await db.commit()

            elif tool_name == "create_standing_instruction":
                # Save instruction draft — awaits trader approval via /instructions endpoint
                pass
            elif tool_name == "propose_risk_limit_update":
                from routers.risk_limits import persist_risk_limit_draft

                draft_data.update(await persist_risk_limit_draft(
                    db,
                    draft_data["limit_type"],
                    draft_data["value"],
                ))

        # Stream agent response. Convert callback/database failures into an SSE
        # error so the browser does not see a dropped connection as "Failed to fetch".
        try:
            async for chunk in agent.stream(messages, on_draft=on_draft):
                yield chunk
        except Exception:
            await db.rollback()
            logger.exception("Chat response stream failed")
            yield f"data: {json.dumps({'type': 'error', 'content': 'The copilot could not complete this request. No broker order was submitted. Check service health and retry.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


@router.get("/price-snapshot")
async def price_snapshot(request: Request):
    """Return the latest price snapshot from Redis (for the ticker strip)."""
    redis = request.app.state.redis
    raw = await redis.get("price:snapshot")
    if raw:
        return json.loads(raw)
    return {"prices": {}, "updated_at": None}
