"""
Audit Logger — writes immutable audit log entries to PostgreSQL.
Every significant event in the system is recorded here.
"""
import json
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class AuditLogger:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        event_type: str,
        order_id: Optional[UUID] = None,
        instruction_id: Optional[UUID] = None,
        actor: str = "TRADER",
        payload: Optional[dict] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Write an audit log entry."""
        await self.db.execute(
            text("""
                INSERT INTO audit_log (event_type, order_id, instruction_id, actor, payload, ip_address)
                VALUES (:event_type, :order_id, :instruction_id, :actor, CAST(:payload AS jsonb), :ip)
            """),
            {
                "event_type":      event_type,
                "order_id":        str(order_id) if order_id else None,
                "instruction_id":  str(instruction_id) if instruction_id else None,
                "actor":           actor,
                "payload":         json.dumps(payload or {}),
                "ip":              ip_address,
            },
        )
        # Note: caller is responsible for committing the session
