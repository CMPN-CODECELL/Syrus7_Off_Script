"""
Standing Instructions Service + Background Runner.

Rules are stored in PostgreSQL, loaded on startup, and checked against live prices.
Each rule fires exactly once — triggered_at is stamped atomically.
Rules that become stale (no price feed) are paused, not silently dropped.
"""

import asyncio
import json
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker



class StandingInstructionRunner:
    """
    Background task that polls active standing instructions
    and fires them when their condition is met.
    """

    def __init__(self, session_factory: async_sessionmaker, redis: aioredis.Redis):
        self.session_factory = session_factory
        self.redis = redis
        self._running = False
        self.poll_interval = 5  # seconds

    async def start(self):
        self._running = True
        print("📋 Standing instruction runner: started")
        while self._running:
            try:
                await self._check_instructions()
            except Exception as e:
                print(f"⚠️  Instruction runner error: {e}")
            await asyncio.sleep(self.poll_interval)

    def stop(self):
        self._running = False

    async def _get_price(self, symbol: str) -> Optional[float]:
        """Get current price from Redis (set by price poller)."""
        try:
            val = await self.redis.get(f"price:{symbol}")
            return float(val) if val else None
        except Exception:
            return None

    async def _check_instructions(self):
        """Check all active instructions against current prices."""
        async with self.session_factory() as db:
            expired = await db.execute(
                text("""UPDATE standing_instructions
                    SET status = 'EXPIRED'
                    WHERE status IN ('ACTIVE', 'PAUSED')
                    AND expires_at IS NOT NULL AND expires_at <= NOW()
                    RETURNING id, name""")
            )
            from services.audit_logger import AuditLogger
            for rule in expired.mappings():
                await AuditLogger(db).log(
                    event_type="INSTRUCTION_EXPIRED",
                    instruction_id=rule["id"],
                    actor="SYSTEM",
                    payload={"name": rule["name"]},
                )
            await db.commit()

            # A process can stop after claiming a rule or at any point between
            # draft creation, approval, and broker acknowledgement. Resume its
            # deterministic order instead of silently losing the rule or
            # creating another client order.
            pending = await db.execute(
                text("""SELECT * FROM standing_instructions
                    WHERE status = 'TRIGGERED'""")
            )
            for inst in pending.mappings().fetchall():
                await self._resume_triggered(db, inst)

            result = await db.execute(
                text("""
                    SELECT * FROM standing_instructions
                    WHERE status = 'ACTIVE'
                    AND (expires_at IS NULL OR expires_at > NOW())
                """)
            )
            instructions = result.mappings().fetchall()

            for inst in instructions:
                symbol = inst["symbol"]
                price = await self._get_price(symbol)

                if price is None:
                    # No price data — pause the instruction (safety rule: don't fire blind)
                    await db.execute(
                        text("UPDATE standing_instructions SET status = 'PAUSED' WHERE id = :id"),
                        {"id": str(inst["id"])},
                    )
                    from services.audit_logger import AuditLogger
                    await AuditLogger(db).log(
                        event_type="INSTRUCTION_PAUSED_STALE_QUOTE",
                        instruction_id=inst["id"],
                        actor="SYSTEM",
                        payload={"symbol": symbol, "reason": "No current price is available."},
                    )
                    await db.commit()
                    continue

                condition_met = self._evaluate_condition(
                    condition_type=inst["condition_type"],
                    condition_value=float(inst["condition_value"]),
                    current_price=price,
                )

                if condition_met:
                    await self._trigger(db, inst, price)

    def _evaluate_condition(self, condition_type: str, condition_value: float, current_price: float) -> bool:
        if condition_type == "PRICE_ABOVE":
            return current_price >= condition_value
        elif condition_type == "PRICE_BELOW":
            return current_price <= condition_value
        elif condition_type == "PERCENT_CHANGE":
            # condition_value is the % threshold (positive or negative)
            # This would need a reference price — simplified for demo
            return False
        return False

    async def _trigger(self, db: AsyncSession, inst, current_price: float):
        """Claim a pre-approved rule once, then route its order through normal risk and execution controls."""
        result = await db.execute(
            text("""UPDATE standing_instructions
                SET status = 'TRIGGERED', triggered_at = NOW()
                WHERE id = :id AND status = 'ACTIVE' AND triggered_at IS NULL
                RETURNING id"""),
            {"id": str(inst["id"])},
        )
        if not result.fetchone():
            return
        await db.commit()

        await self._process_triggered(db, inst, current_price)

    @staticmethod
    def _client_order_id(instruction_id) -> str:
        """Stable idempotency key, so a restart reuses the same order intent."""
        return f"SI-{str(instruction_id).replace('-', '').upper()}"

    async def _resume_triggered(self, db: AsyncSession, inst):
        """Resume a previously claimed rule after a process restart."""
        from services.audit_logger import AuditLogger
        from services.executor import ExecutorService
        from services.order_service import OrderService

        try:
            order_id = inst.get("triggered_order_id")
            if not order_id:
                # Recover the order if it was committed before the rule link.
                found = await db.execute(
                    text("SELECT id, status, approval_token FROM orders WHERE client_order_id = :coid"),
                    {"coid": self._client_order_id(inst["id"])},
                )
                existing = found.mappings().fetchone()
                if existing:
                    order_id = existing["id"]
                    await db.execute(
                        text("UPDATE standing_instructions SET triggered_order_id = :oid WHERE id = :id AND triggered_order_id IS NULL"),
                        {"oid": str(order_id), "id": str(inst["id"])},
                    )
                    await db.commit()
                else:
                    price = await self._get_price(inst["symbol"])
                    if price is None:
                        return
                    await self._process_triggered(db, inst, price)
                    return

            order = await OrderService(db).get(str(order_id))
            if not order:
                return
            executor = ExecutorService(db)
            if order["status"] == "DRAFT":
                approval = await OrderService(db).approve(str(order_id))
                result = await executor.execute(str(order_id), approval["token"])
            elif order["status"] == "APPROVED" and order.get("approval_token"):
                result = await executor.execute(str(order_id), order["approval_token"])
            elif order["status"] == "SUBMITTED":
                result = await executor.reconcile(str(order_id))
            else:
                return

            if result.status == "PRICE_DRIFTED":
                await self._pause_on_price_drift(db, inst, order_id, result.message)

            await AuditLogger(db).log(
                event_type="INSTRUCTION_RECOVERED",
                order_id=order_id,
                instruction_id=inst["id"],
                actor="SYSTEM",
                payload={"order_status": result.status, "message": result.message},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await AuditLogger(db).log(
                event_type="INSTRUCTION_RECOVERY_ERROR",
                instruction_id=inst["id"],
                actor="SYSTEM",
                payload={"error": str(exc)},
            )
            await db.commit()

    async def _process_triggered(self, db: AsyncSession, inst, current_price: float):
        """Create/link one durable order for a claimed rule, then execute it."""

        from services.audit_logger import AuditLogger
        from services.executor import ExecutorService
        from services.order_service import OrderService
        from services.risk_engine import RiskBudgetEngine

        order = None
        try:
            draft_data = {
                "symbol": inst["symbol"],
                "side": inst["action_side"],
                "order_type": inst["action_order_type"],
                "quantity": inst["action_quantity"],
                "quoted_price": current_price,
            }
            risk = await RiskBudgetEngine(db).check_order(draft_data)
            if not risk.passed:
                await db.execute(
                    text("UPDATE standing_instructions SET status = 'PAUSED' WHERE id = :id AND status = 'TRIGGERED'"),
                    {"id": str(inst["id"])},
                )
                await AuditLogger(db).log(
                    event_type="INSTRUCTION_BLOCKED_BY_RISK",
                    instruction_id=inst["id"],
                    actor="SYSTEM",
                    payload={"reason": risk.reason, "trigger_price": current_price},
                )
                await db.commit()
                return

            draft_data["risk_score"] = risk.score
            draft_data["risk_check_passed"] = True
            order = await OrderService(db).create_draft(
                raw_message=f"Standing instruction: {inst['name']}",
                draft_data=draft_data,
                client_order_id=self._client_order_id(inst["id"]),
            )
            await db.execute(
                text("UPDATE standing_instructions SET triggered_order_id = :oid WHERE id = :id AND triggered_order_id IS NULL"),
                {"oid": str(order.id), "id": str(inst["id"])},
            )
            await db.commit()

            order_service = OrderService(db)
            approval = await order_service.approve(str(order.id))
            execution = await ExecutorService(db).execute(str(order.id), approval["token"])

            if execution.status == "PRICE_DRIFTED":
                await self._pause_on_price_drift(db, inst, order.id, execution.message)

            await AuditLogger(db).log(
                event_type="INSTRUCTION_TRIGGERED",
                order_id=order.id,
                instruction_id=inst["id"],
                actor="SYSTEM",
                payload={
                    "instruction_name": inst["name"],
                    "trigger_price": current_price,
                    "order_status": execution.status,
                    "execution_message": execution.message,
                },
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            await AuditLogger(db).log(
                event_type="INSTRUCTION_EXECUTION_ERROR",
                order_id=order.id if order else None,
                instruction_id=inst["id"],
                actor="SYSTEM",
                payload={"error": str(exc), "trigger_price": current_price},
            )
            await db.commit()

    async def _pause_on_price_drift(self, db: AsyncSession, inst, order_id, reason: str):
        """Stop an automated rule after its approved trigger quote goes stale."""
        from services.audit_logger import AuditLogger

        await db.execute(
            text("UPDATE standing_instructions SET status = 'PAUSED' WHERE id = :id AND status = 'TRIGGERED'"),
            {"id": str(inst["id"])},
        )
        await AuditLogger(db).log(
            event_type="INSTRUCTION_PAUSED_PRICE_DRIFT",
            order_id=order_id,
            instruction_id=inst["id"],
            actor="SYSTEM",
            payload={"reason": reason},
        )
        await db.commit()
