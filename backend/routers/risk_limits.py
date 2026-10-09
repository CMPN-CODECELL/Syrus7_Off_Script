"""Read and explicitly approve persisted mock-mode risk-budget proposals."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.audit_logger import AuditLogger
from services.risk_engine import CONFIGURABLE_LIMITS, DEFAULT_LIMITS, validate_limit_value

router = APIRouter()
RISK_LIMIT_DRAFT_TTL_SECONDS = 60


async def persist_risk_limit_draft(db: AsyncSession, limit_type: str, proposed_value) -> dict:
    """Save a validated proposal so the browser can approve only this exact change."""
    value = validate_limit_value(limit_type, proposed_value)
    current_result = await db.execute(
        text("""SELECT value_numeric FROM risk_limits
            WHERE limit_type = :kind AND is_active = TRUE
            ORDER BY created_at DESC LIMIT 1"""),
        {"kind": limit_type},
    )
    current = current_result.mappings().fetchone()
    old_value = (
        float(current["value_numeric"])
        if current and current["value_numeric"] is not None
        else DEFAULT_LIMITS[limit_type]
    )
    draft_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=RISK_LIMIT_DRAFT_TTL_SECONDS)
    await db.execute(
        text("""INSERT INTO risk_limit_drafts (id, limit_type, old_value, new_value, expires_at)
            VALUES (:id, :kind, :old, :new, :expires)"""),
        {"id": draft_id, "kind": limit_type, "old": old_value, "new": value, "expires": expires_at},
    )
    await AuditLogger(db).log(
        event_type="RISK_LIMIT_CHANGE_PROPOSED",
        actor="TRADER",
        payload={"draft_id": draft_id, "limit_type": limit_type, "old_value": old_value, "new_value": value},
    )
    await db.commit()
    return {
        "draft_id": draft_id,
        "limit_type": limit_type,
        "label": CONFIGURABLE_LIMITS[limit_type]["label"],
        "current_value": old_value,
        "value": value,
        "expires_at": expires_at.isoformat(),
    }


@router.get("/")
async def get_risk_limits(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text(
        "SELECT limit_type, value_numeric FROM risk_limits "
        "WHERE is_active = TRUE ORDER BY created_at, id"
    ))
    current = dict(DEFAULT_LIMITS)
    for row in result.mappings():
        if row["limit_type"] in CONFIGURABLE_LIMITS and row["value_numeric"] is not None:
            current[row["limit_type"]] = float(row["value_numeric"])
    return {
        "limits": [
            {
                "limit_type": key,
                "label": CONFIGURABLE_LIMITS[key]["label"],
                "value": current[key],
                "hard_max": CONFIGURABLE_LIMITS[key]["hard_max"],
            }
            for key in CONFIGURABLE_LIMITS
        ]
    }


@router.get("/drafts/{draft_id}")
async def get_risk_limit_draft(draft_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM risk_limit_drafts WHERE id = :id"),
        {"id": draft_id},
    )
    draft = result.mappings().fetchone()
    if not draft:
        raise HTTPException(status_code=404, detail="Risk-budget proposal not found")
    status = draft["status"]
    if status == "DRAFT" and draft["expires_at"] <= datetime.now(timezone.utc):
        await db.execute(
            text("UPDATE risk_limit_drafts SET status = 'EXPIRED' WHERE id = :id AND status = 'DRAFT'"),
            {"id": draft_id},
        )
        await AuditLogger(db).log(
            event_type="RISK_LIMIT_CHANGE_EXPIRED",
            actor="SYSTEM",
            payload={"draft_id": draft_id, "limit_type": draft["limit_type"]},
        )
        await db.commit()
        status = "EXPIRED"
    return {
        "draft_id": str(draft["id"]),
        "status": status,
        "limit_type": draft["limit_type"],
        "label": CONFIGURABLE_LIMITS[draft["limit_type"]]["label"],
        "previous_value": float(draft["old_value"]),
        "value": float(draft["new_value"]),
        "expires_at": draft["expires_at"].isoformat(),
    }


@router.post("/drafts/{draft_id}/approve")
async def approve_risk_limit_draft(draft_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM risk_limit_drafts WHERE id = :id FOR UPDATE"),
        {"id": draft_id},
    )
    draft = result.mappings().fetchone()
    if not draft:
        raise HTTPException(status_code=404, detail="Risk-budget proposal not found")
    if draft["status"] == "APPROVED":
        return {
            "success": True,
            "already_applied": True,
            "limit_type": draft["limit_type"],
            "label": CONFIGURABLE_LIMITS[draft["limit_type"]]["label"],
            "previous_value": float(draft["old_value"]),
            "value": float(draft["new_value"]),
            "message": "This risk-budget change was already approved and applied.",
        }
    if draft["status"] != "DRAFT":
        raise HTTPException(status_code=409, detail=f"This proposal is already {draft['status'].lower()}.")

    if draft["expires_at"] <= datetime.now(timezone.utc):
        await db.execute(
            text("UPDATE risk_limit_drafts SET status = 'EXPIRED' WHERE id = :id AND status = 'DRAFT'"),
            {"id": draft_id},
        )
        await AuditLogger(db).log(
            event_type="RISK_LIMIT_CHANGE_EXPIRED",
            actor="SYSTEM",
            payload={"draft_id": draft_id, "limit_type": draft["limit_type"]},
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="This proposal expired. Ask StockItUp to create a fresh one.")

    current_result = await db.execute(
        text("""SELECT value_numeric FROM risk_limits
            WHERE limit_type = :kind AND is_active = TRUE
            ORDER BY created_at DESC LIMIT 1 FOR UPDATE"""),
        {"kind": draft["limit_type"]},
    )
    current = current_result.mappings().fetchone()
    current_value = (
        Decimal(str(current["value_numeric"]))
        if current and current["value_numeric"] is not None
        else Decimal(str(DEFAULT_LIMITS[draft["limit_type"]]))
    )
    if current_value != Decimal(str(draft["old_value"])):
        await db.execute(
            text("UPDATE risk_limit_drafts SET status = 'STALE' WHERE id = :id AND status = 'DRAFT'"),
            {"id": draft_id},
        )
        await AuditLogger(db).log(
            event_type="RISK_LIMIT_CHANGE_STALE",
            actor="SYSTEM",
            payload={"draft_id": draft_id, "limit_type": draft["limit_type"], "current_value": float(current_value)},
        )
        await db.commit()
        raise HTTPException(status_code=409, detail="The risk limit changed after this proposal. Review a fresh proposal.")

    claimed = await db.execute(
        text("""UPDATE risk_limit_drafts SET status = 'APPROVED', approved_at = NOW()
            WHERE id = :id AND status = 'DRAFT' AND expires_at > NOW() RETURNING id"""),
        {"id": draft_id},
    )
    if not claimed.fetchone():
        await db.rollback()
        raise HTTPException(status_code=409, detail="This proposal expired or was already handled.")

    updated = await db.execute(
        text("""UPDATE risk_limits SET value_numeric = :value, is_active = TRUE
            WHERE limit_type = :kind RETURNING id"""),
        {"kind": draft["limit_type"], "value": draft["new_value"]},
    )
    if not updated.fetchall():
        await db.execute(
            text("""INSERT INTO risk_limits (limit_name, limit_type, value_numeric, is_active)
                VALUES (:name, :kind, :value, TRUE)"""),
            {
                "name": draft["limit_type"].lower(),
                "kind": draft["limit_type"],
                "value": draft["new_value"],
            },
        )

    await AuditLogger(db).log(
        event_type="RISK_LIMIT_UPDATED",
        actor="TRADER",
        payload={
            "draft_id": draft_id,
            "limit_type": draft["limit_type"],
            "old_value": float(draft["old_value"]),
            "new_value": float(draft["new_value"]),
        },
    )
    await db.commit()
    return {
        "success": True,
        "limit_type": draft["limit_type"],
        "label": CONFIGURABLE_LIMITS[draft["limit_type"]]["label"],
        "previous_value": float(draft["old_value"]),
        "value": float(draft["new_value"]),
        "message": "Risk budget updated and recorded in the audit log.",
    }


@router.post("/drafts/{draft_id}/reject")
async def reject_risk_limit_draft(draft_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT limit_type FROM risk_limit_drafts WHERE id = :id AND status = 'DRAFT' FOR UPDATE"),
        {"id": draft_id},
    )
    draft = result.mappings().fetchone()
    if not draft:
        raise HTTPException(status_code=404, detail="Open risk-budget proposal not found")
    await db.execute(
        text("UPDATE risk_limit_drafts SET status = 'REJECTED', rejected_at = NOW() WHERE id = :id AND status = 'DRAFT'"),
        {"id": draft_id},
    )
    await AuditLogger(db).log(
        event_type="RISK_LIMIT_CHANGE_REJECTED",
        actor="TRADER",
        payload={"draft_id": draft_id, "limit_type": draft["limit_type"]},
    )
    await db.commit()
    return {"success": True, "message": "Risk-budget proposal rejected; no limit was changed."}
