"""
Audit Log Router — read-only view of the audit trail.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter()


@router.get("/")
async def get_audit_log(limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""
            SELECT al.*, o.symbol, o.side, o.quantity
            FROM audit_log al
            LEFT JOIN orders o ON al.order_id = o.id
            ORDER BY al.created_at DESC
            LIMIT :limit
        """),
        {"limit": limit},
    )
    return {"entries": [dict(r) for r in result.mappings()]}


@router.get("/narrative")
async def get_narrative_report(db: AsyncSession = Depends(get_db)):
    """
    Generate a plain-English narrative of today's trading activity using Gemini.
    One of the USP features from the proposal.
    """
    result = await db.execute(
        text("""
            SELECT o.*, al.event_type, al.created_at as event_time
            FROM orders o
            JOIN audit_log al ON al.order_id = o.id
            WHERE DATE(o.created_at) = CURRENT_DATE
            AND al.event_type IN ('ORDER_EXECUTED', 'ORDER_REJECTED', 'INSTRUCTION_TRIGGERED')
            ORDER BY al.created_at ASC
        """)
    )
    rows = result.mappings().fetchall()

    if not rows:
        return {"narrative": "No trading activity recorded today.", "orders": []}

    # Summarise data for Gemini
    import json
    from google import genai
    from config import settings

    summary_data = [dict(r) for r in rows]
    # Convert UUID/decimal to serializable
    for row in summary_data:
        for k, v in row.items():
            if hasattr(v, 'isoformat'):
                row[k] = v.isoformat()
            elif str(type(v)) == "<class 'decimal.Decimal'>":
                row[k] = float(v)

    prompt = (
        "You are StockItUp, a trading copilot. Write a concise, clear, 3-5 sentence "
        "plain-English narrative summary of today's trading activity based on this data. "
        "Mention total orders, key stocks traded, overall P&L direction if inferable, "
        "and any rejected or partial fills. Be direct, no fluff.\n\n"
        f"Data: {json.dumps(summary_data, default=str)}"
    )

    if not settings.gemini_api_key:
        return {"narrative": "Gemini is not configured. Set GEMINI_API_KEY and restart the backend.", "orders": summary_data}

    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
    )
    return {
        "narrative": response.text or "No narrative was returned.",
        "orders": summary_data,
    }
