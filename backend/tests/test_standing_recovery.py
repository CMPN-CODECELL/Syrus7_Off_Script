import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.standing_instructions import StandingInstructionRunner


class FakeDB:
    def __init__(self):
        self.statements = []
        self.commits = 0

    async def execute(self, statement, params=None):
        self.statements.append((str(statement), params or {}))
        return EmptyResult()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class EmptyResult:
    def mappings(self):
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class FakeRedis:
    async def get(self, key):
        return "100.00"


class StandingInstructionRecoveryTests(unittest.TestCase):
    def test_paused_rule_expires_and_is_audited(self):
        audit_events = []
        db = FakeDB()

        class ExpiryResult:
            def mappings(self):
                return self

            def __iter__(self):
                return iter([{"id": "paused-rule", "name": "Expired paused rule"}])

            def fetchall(self):
                return []

        class ExpiryDB(FakeDB):
            async def execute(self, statement, params=None):
                self.statements.append((str(statement), params or {}))
                if "RETURNING id, name" in str(statement):
                    return ExpiryResult()
                return EmptyResult()

        class Session:
            async def __aenter__(self):
                return db

            async def __aexit__(self, *_args):
                return False

        # Use the specialized fake for this query and preserve commit tracking.
        db = ExpiryDB()

        class FakeAuditLogger:
            def __init__(self, _db):
                pass

            async def log(self, **kwargs):
                audit_events.append(kwargs)

        runner = StandingInstructionRunner(lambda: Session(), FakeRedis())
        with patch("services.audit_logger.AuditLogger", FakeAuditLogger):
            asyncio.run(runner._check_instructions())

        expiry_sql = next(sql for sql, _ in db.statements if "RETURNING id, name" in sql)
        self.assertIn("status IN ('ACTIVE', 'PAUSED')", expiry_sql)
        self.assertEqual(audit_events[0]["event_type"], "INSTRUCTION_EXPIRED")
        self.assertEqual(audit_events[0]["instruction_id"], "paused-rule")

    def test_rule_order_id_is_stable_across_restarts(self):
        rule_id = "a0b1c2d3-e4f5-6789-abcd-ef0123456789"
        first = StandingInstructionRunner._client_order_id(rule_id)
        second = StandingInstructionRunner._client_order_id(rule_id)
        self.assertEqual(first, second)
        self.assertEqual(first, "SI-A0B1C2D3E4F56789ABCDEF0123456789")

    def test_approved_order_is_resumed_with_existing_token(self):
        calls = []

        class FakeOrderService:
            def __init__(self, db):
                pass

            async def get(self, order_id):
                return {"status": "APPROVED", "approval_token": "persisted-token"}

        class FakeExecutor:
            def __init__(self, db):
                pass

            async def execute(self, order_id, token):
                calls.append(("execute", order_id, token))
                return SimpleNamespace(status="FILLED", message="mock fill")

            async def reconcile(self, order_id):
                calls.append(("reconcile", order_id))
                return SimpleNamespace(status="FILLED", message="mock fill")

        class FakeAuditLogger:
            def __init__(self, db):
                pass

            async def log(self, **kwargs):
                calls.append(("audit", kwargs["event_type"]))

        runner = StandingInstructionRunner(None, None)
        rule = {
            "id": "rule-id",
            "triggered_order_id": "order-id",
        }
        with patch("services.order_service.OrderService", FakeOrderService), patch(
            "services.executor.ExecutorService", FakeExecutor
        ), patch("services.audit_logger.AuditLogger", FakeAuditLogger):
            asyncio.run(runner._resume_triggered(FakeDB(), rule))

        self.assertIn(("execute", "order-id", "persisted-token"), calls)
        self.assertIn(("audit", "INSTRUCTION_RECOVERED"), calls)
        self.assertFalse(any(call[0] == "reconcile" for call in calls))

    def test_submitted_order_is_reconciled_instead_of_resubmitted(self):
        calls = []

        class FakeOrderService:
            def __init__(self, db):
                pass

            async def get(self, order_id):
                return {"status": "SUBMITTED", "approval_token": "persisted-token"}

        class FakeExecutor:
            def __init__(self, db):
                pass

            async def execute(self, order_id, token):
                calls.append(("execute", order_id))
                raise AssertionError("uncertain submissions must not be resubmitted")

            async def reconcile(self, order_id):
                calls.append(("reconcile", order_id))
                return SimpleNamespace(status="FILLED", message="reconciled")

        class FakeAuditLogger:
            def __init__(self, db):
                pass

            async def log(self, **kwargs):
                calls.append(("audit", kwargs["event_type"]))

        runner = StandingInstructionRunner(None, None)
        rule = {"id": "rule-id", "triggered_order_id": "order-id"}
        with patch("services.order_service.OrderService", FakeOrderService), patch(
            "services.executor.ExecutorService", FakeExecutor
        ), patch("services.audit_logger.AuditLogger", FakeAuditLogger):
            asyncio.run(runner._resume_triggered(FakeDB(), rule))

        self.assertIn(("reconcile", "order-id"), calls)
        self.assertFalse(any(call[0] == "execute" for call in calls))

    def test_unlinked_trigger_reuses_deterministic_client_id_to_create_its_order(self):
        created = []
        calls = []

        class FakeOrderService:
            def __init__(self, db):
                pass

            async def create_draft(self, raw_message, draft_data, client_order_id):
                created.append(client_order_id)
                return SimpleNamespace(id="new-order-id")

            async def approve(self, order_id):
                calls.append(("approve", order_id))
                return {"token": "approval-token"}

        class FakeRiskEngine:
            def __init__(self, db):
                pass

            async def check_order(self, draft):
                self.draft = draft
                return SimpleNamespace(passed=True, score=95, reason="")

        class FakeExecutor:
            def __init__(self, db):
                pass

            async def execute(self, order_id, token):
                calls.append(("execute", order_id, token))
                return SimpleNamespace(status="FILLED", message="mock fill")

        class FakeAuditLogger:
            def __init__(self, db):
                pass

            async def log(self, **kwargs):
                calls.append(("audit", kwargs["event_type"]))

        rule = {
            "id": "a0b1c2d3-e4f5-6789-abcd-ef0123456789",
            "triggered_order_id": None,
            "symbol": "INFY.NS",
            "name": "Test rule",
            "action_side": "BUY",
            "action_order_type": "MARKET",
            "action_quantity": 1,
        }
        db = FakeDB()
        runner = StandingInstructionRunner(None, FakeRedis())
        with patch("services.order_service.OrderService", FakeOrderService), patch(
            "services.executor.ExecutorService", FakeExecutor
        ), patch("services.risk_engine.RiskBudgetEngine", FakeRiskEngine), patch(
            "services.audit_logger.AuditLogger", FakeAuditLogger
        ):
            asyncio.run(runner._resume_triggered(db, rule))

        expected_client_id = "SI-A0B1C2D3E4F56789ABCDEF0123456789"
        self.assertEqual(created, [expected_client_id])
        self.assertIn(("approve", "new-order-id"), calls)
        self.assertIn(("execute", "new-order-id", "approval-token"), calls)
        self.assertTrue(any("triggered_order_id = :oid" in sql for sql, _ in db.statements))
        self.assertGreaterEqual(db.commits, 2)


if __name__ == "__main__":
    unittest.main()
