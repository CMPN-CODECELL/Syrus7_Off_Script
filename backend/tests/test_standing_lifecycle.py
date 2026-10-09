import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.standing_instructions import StandingInstructionRunner


class Result:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row

    def mappings(self):
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row

    def __iter__(self):
        return iter(self.rows)


class RuleDB:
    def __init__(self, rule):
        self.rule = rule.copy()
        self.commits = 0
        self.statements = []

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if "SET status = 'EXPIRED'" in sql:
            return Result()
        if "WHERE status = 'TRIGGERED'" in sql:
            return Result(rows=[self.rule.copy()] if self.rule["status"] == "TRIGGERED" else [])
        if "WHERE status = 'ACTIVE'" in sql and sql.lstrip().startswith("SELECT"):
            return Result(rows=[self.rule.copy()] if self.rule["status"] == "ACTIVE" else [])
        if "SET status = 'TRIGGERED'" in sql:
            if self.rule["status"] != "ACTIVE" or self.rule["triggered_at"] is not None:
                return Result()
            self.rule.update({"status": "TRIGGERED", "triggered_at": "now"})
            return Result(row={"id": self.rule["id"]})
        if "SET triggered_order_id = :oid" in sql:
            self.rule["triggered_order_id"] = (params or {})["oid"]
            return Result(row={"id": self.rule["id"]})
        return Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


class Redis:
    async def get(self, _key):
        return "100"


class Session:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return False


class StandingInstructionLifecycleTests(unittest.TestCase):
    def test_active_rule_triggers_once_and_persists_linked_mock_order(self):
        rule = {
            "id": "rule-1", "name": "TCS above 99", "symbol": "TCS.NS",
            "condition_type": "PRICE_ABOVE", "condition_value": 99,
            "action_side": "BUY", "action_order_type": "MARKET", "action_quantity": 1,
            "status": "ACTIVE", "triggered_at": None, "triggered_order_id": None,
        }
        db = RuleDB(rule)
        calls = []

        class Risk:
            def __init__(self, _db):
                pass

            async def check_order(self, _draft):
                return SimpleNamespace(passed=True, score=95, reason="")

        class Orders:
            def __init__(self, _db):
                pass

            async def create_draft(self, **kwargs):
                calls.append(("create", kwargs["client_order_id"]))
                return SimpleNamespace(id="order-1")

            async def approve(self, order_id):
                calls.append(("approve", order_id))
                return {"token": "one-time-token"}

            async def get(self, order_id):
                return {"id": order_id, "status": "FILLED", "approval_token": None}

        class Executor:
            def __init__(self, _db):
                pass

            async def execute(self, order_id, token):
                calls.append(("execute", order_id, token))
                return SimpleNamespace(status="FILLED", message="simulated fill")

            async def reconcile(self, order_id):
                raise AssertionError("a filled rule order should not be reconciled")

        class Audit:
            def __init__(self, _db):
                pass

            async def log(self, **kwargs):
                calls.append(("audit", kwargs["event_type"]))

        runner = StandingInstructionRunner(lambda: Session(db), Redis())
        patches = [
            patch("services.risk_engine.RiskBudgetEngine", Risk),
            patch("services.order_service.OrderService", Orders),
            patch("services.executor.ExecutorService", Executor),
            patch("services.audit_logger.AuditLogger", Audit),
        ]
        with patches[0], patches[1], patches[2], patches[3]:
            asyncio.run(runner._check_instructions())
            asyncio.run(runner._check_instructions())

        self.assertEqual(db.rule["status"], "TRIGGERED")
        self.assertEqual(db.rule["triggered_order_id"], "order-1")
        self.assertEqual(sum(call[0] == "execute" for call in calls), 1)
        self.assertEqual(sum(call[0] == "create" for call in calls), 1)
        self.assertTrue(any(call == ("audit", "INSTRUCTION_TRIGGERED") for call in calls))
        self.assertIn("triggered_order_id = :oid", "\n".join(db.statements))


if __name__ == "__main__":
    unittest.main()
