"""
Standing Instructions Router — CRUD for standing rules.
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal, Optional

from services.instruments import canonical_symbol

from db import get_db

router = APIRouter()


class CreateInstructionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    symbol: str
    condition_type: Literal["PRICE_ABOVE", "PRICE_BELOW"]
    condition_value: float = Field(gt=0, allow_inf_nan=False)
    action_side: Literal["BUY", "SELL"]
    action_quantity: int = Field(gt=0, le=1000)
    action_order_type: Literal["MARKET"] = "MARKET"
    expires_in_hours: Optional[float] = Field(default=None, gt=0, le=720, allow_inf_nan=False)
    raw_instruction: str = Field(default="", max_length=2000)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        return canonical_symbol(value)


@router.post("/")
async def create_instruction(req: CreateInstructionRequest, db: AsyncSession = Depends(get_db)):
    """Create a standing instruction after the trader confirms its preview."""
    import uuid
    from datetime import datetime, timezone, timedelta

    expires_at = None
    if req.expires_in_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=req.expires_in_hours)

    inst_id = uuid.uuid4()
    await db.execute(
        text("""
            INSERT INTO standing_instructions (
                id, name, raw_instruction, symbol,
                condition_type, condition_value,
                action_side, action_order_type, action_quantity,
                status, expires_at, approved_at
            ) VALUES (
                :id, :name, :raw, :symbol,
                :ctype, :cval,
                :aside, :aotype, :aqty,
                'ACTIVE', :expires_at, NOW()
            )
        """),
        {
            "id": str(inst_id),
            "name": req.name,
            "raw": req.raw_instruction or req.name,
            "symbol": req.symbol,
            "ctype": req.condition_type,
            "cval": req.condition_value,
            "aside": req.action_side,
            "aotype": req.action_order_type,
            "aqty": req.action_quantity,
            "expires_at": expires_at,
        },
    )
    import json
    await db.execute(
        text("""INSERT INTO audit_log (event_type, instruction_id, actor, payload)
            VALUES ('INSTRUCTION_ACTIVATED', :iid, 'TRADER', CAST(:payload AS jsonb))"""),
        {
            "iid": str(inst_id),
            "payload": json.dumps({
                "name": req.name,
                "symbol": req.symbol,
                "condition_type": req.condition_type,
                "condition_value": req.condition_value,
                "action_side": req.action_side,
                "action_quantity": req.action_quantity,
                "action_order_type": req.action_order_type,
                "expires_at": expires_at.isoformat() if expires_at else None,
            }),
        },
    )
    await db.commit()
    return {"id": str(inst_id), "status": "ACTIVE", "message": "Standing instruction created and active."}


@router.get("/")
async def list_instructions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM standing_instructions ORDER BY created_at DESC LIMIT 50")
    )
    return {"instructions": [dict(r) for r in result.mappings()]}


@router.post("/{instruction_id}/resume")
async def resume_instruction(instruction_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Resume a rule paused before it fired, but only while a fresh quote exists."""
    result = await db.execute(
        text("SELECT symbol, triggered_at FROM standing_instructions WHERE id = :id AND status = 'PAUSED'"),
        {"id": instruction_id},
    )
    inst = result.mappings().fetchone()
    if not inst:
        raise HTTPException(status_code=404, detail="Paused instruction not found")
    if inst["triggered_at"] is not None:
        raise HTTPException(
            status_code=409,
            detail="This instruction already fired and cannot be resumed. Cancel it and create a new rule after reviewing it.",
        )

    try:
        quote = await request.app.state.redis.get(f"price:{inst['symbol']}")
        if not quote or float(quote) <= 0:
            raise ValueError("missing quote")
    except (ValueError, TypeError):
        raise HTTPException(status_code=409, detail="A fresh quote is unavailable. The instruction remains paused.")

    updated = await db.execute(
        text("UPDATE standing_instructions SET status = 'ACTIVE' WHERE id = :id AND status = 'PAUSED' AND triggered_at IS NULL RETURNING id"),
        {"id": instruction_id},
    )
    if not updated.fetchone():
        await db.rollback()
        raise HTTPException(status_code=409, detail="Instruction changed while resuming. Refresh and try again.")
    await db.execute(
        text("""INSERT INTO audit_log (event_type, instruction_id, actor, payload)
            VALUES ('INSTRUCTION_RESUMED', :iid, 'TRADER', CAST(:payload AS jsonb))"""),
        {"iid": instruction_id, "payload": json.dumps({"symbol": inst["symbol"]})},
    )
    await db.commit()
    return {"success": True, "status": "ACTIVE", "message": "Instruction resumed with a fresh quote."}


@router.delete("/{instruction_id}")
async def cancel_instruction(instruction_id: str, db: AsyncSession = Depends(get_db)):
    """Trader cancels an active or safely paused standing instruction."""
    result = await db.execute(
        text("""
            UPDATE standing_instructions
            SET status = 'CANCELLED', cancelled_at = NOW()
            WHERE id = :id AND status IN ('ACTIVE', 'PAUSED')
            RETURNING id
        """),
        {"id": instruction_id},
    )
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Instruction not found or cannot be cancelled in its current state")
    await db.execute(
        text("""INSERT INTO audit_log (event_type, instruction_id, actor, payload)
            VALUES ('INSTRUCTION_CANCELLED', :iid, 'TRADER', CAST(:payload AS jsonb))"""),
        {"iid": instruction_id, "payload": json.dumps({"reason": "Trader cancelled instruction"})},
    )
    await db.commit()
    return {"success": True, "message": "Instruction cancelled."}
