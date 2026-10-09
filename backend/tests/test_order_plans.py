import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from routers.orders import approve_order_plan


class Result:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def mappings(self):
        return self

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class FakeDB:
    def __init__(self):
        self.calls = []
        self.plan = {"id": "plan-1", "status": "DRAFT"}
        created = datetime.now(timezone.utc)
        self.orders = [
            {"id": "order-1", "status": "DRAFT", "created_at": created, "symbol": "INFY.NS", "side": "BUY",
             "order_type": "MARKET", "quantity": 10, "price": None, "trigger_price": None, "quoted_price": Decimal("100.00")},
            {"id": "order-2", "status": "DRAFT", "created_at": created, "symbol": "TCS.NS", "side": "SELL",
             "order_type": "MARKET", "quantity": 5, "price": None, "trigger_price": None, "quoted_price": Decimal("100.00")},
        ]

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append(sql)
        if sql.startswith("SELECT * FROM order_plans"):
            return Result(row=self.plan)
        if sql.startswith("SELECT * FROM orders"):
            return Result(rows=self.orders)
        if "SET status='EXECUTING'" in sql:
            return Result(row={"id": "plan-1"})
        return Result()

    async def commit(self):
        pass

    async def rollback(self):
        pass


class FakeRedis:
    async def get(self, _key):
        return "100.00"


def request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=FakeRedis())))


class OrderPlanApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_approval_preflights_and_executes_each_leg_once(self):
        db = FakeDB()
        submitted = []

        class Risk:
            def __init__(self, _db):
                pass

            async def check_order(self, _draft):
                return SimpleNamespace(passed=True, reason="")

        class Orders:
            def __init__(self, _db):
                pass

            async def approve(self, order_id):
                submitted.append(("approve", order_id))
                return {"token": "signed"}

        class Executor:
            def __init__(self, _db):
                pass

            async def execute(self, order_id, _token):
                submitted.append(("execute", order_id))
                return SimpleNamespace(status="FILLED", success=True, message="", filled_quantity=1, average_price=100)

        class Audit:
            def __init__(self, _db):
                pass

            async def log(self, **_kwargs):
                pass

        with patch("routers.orders.RiskBudgetEngine", Risk), patch("routers.orders.OrderService", Orders), \
             patch("routers.orders.ExecutorService", Executor), patch("routers.orders.AuditLogger", Audit):
            result = await approve_order_plan("plan-1", request(), db)

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(len([call for call in submitted if call[0] == "execute"]), 2)
        self.assertIn("SET status='EXECUTING'", " ".join(db.calls))

    async def test_quote_drift_blocks_the_complete_plan_before_any_execution(self):
        db = FakeDB()
        db.orders[1]["quoted_price"] = Decimal("90.00")

        class Risk:
            def __init__(self, _db):
                pass

            async def check_order(self, _draft):
                return SimpleNamespace(passed=True, reason="")

        with patch("routers.orders.RiskBudgetEngine", Risk), patch("routers.orders.ExecutorService") as executor:
            with self.assertRaises(HTTPException) as raised:
                await approve_order_plan("plan-1", request(), db)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertFalse(any("EXECUTING" in sql for sql in db.calls))
        executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
