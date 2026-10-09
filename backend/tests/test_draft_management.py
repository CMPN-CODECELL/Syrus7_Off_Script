import asyncio
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from routers.orders import ModifyDraftRequest, cancel_order_draft, modify_order_draft


class Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self, order=None, update_succeeds=True):
        self.order = order or {
            "id": "order-1", "status": "DRAFT", "symbol": "TCS.NS", "side": "BUY",
            "order_type": "MARKET", "quantity": 10, "price": None,
            "trigger_price": None, "quoted_price": Decimal("4000.00"),
        }
        self.update_succeeds = update_succeeds
        self.calls = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params or {}))
        if sql.startswith("SELECT * FROM orders"):
            return Result(self.order)
        if "RETURNING id" in sql and (sql.startswith("UPDATE orders") or "UPDATE orders SET" in sql):
            return Result({"id": "order-1"} if self.update_succeeds else None)
        return Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


class FakeRedis:
    def __init__(self, quote="4215.75"):
        self.quote = quote

    async def get(self, _key):
        return self.quote


def request(quote="4215.75"):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=FakeRedis(quote))))


class DraftManagementTests(unittest.TestCase):
    def test_edit_schema_rejects_bad_symbols_and_mismatched_prices(self):
        with self.assertRaises(ValueError):
            ModifyDraftRequest(symbol="FAKE.NS", side="BUY", order_type="MARKET", quantity=1)
        with self.assertRaises(ValueError):
            ModifyDraftRequest(symbol="TCS.NS", side="BUY", order_type="LIMIT", quantity=1)
        with self.assertRaises(ValueError):
            ModifyDraftRequest(symbol="TCS.NS", side="BUY", order_type="MARKET", quantity=1, price=100)

    def test_modify_refreshes_quote_rechecks_risk_and_audits(self):
        db = FakeDB()
        audited = []

        class Risk:
            def __init__(self, _db):
                pass

            async def check_order(self, draft):
                self.draft = draft
                return SimpleNamespace(passed=True, score=93, reason="")

        class Audit:
            def __init__(self, _db):
                pass

            async def log(self, **kwargs):
                audited.append(kwargs)

        req = ModifyDraftRequest(symbol="TCS.NS", side="BUY", order_type="MARKET", quantity=5)
        with patch("routers.orders.RiskBudgetEngine", Risk), patch("routers.orders.AuditLogger", Audit):
            response = asyncio.run(modify_order_draft("order-1", req, request(), db))

        update = next(params for sql, params in db.calls if sql.startswith("UPDATE orders SET"))
        self.assertEqual(update["quoted_price"], 4215.75)
        self.assertEqual(update["quantity"], 5)
        self.assertIn("created_at >= NOW()", next(sql for sql, _ in db.calls if sql.startswith("UPDATE orders SET")))
        self.assertEqual(response["status"], "DRAFT")
        self.assertTrue(response["draft"]["risk_check_passed"])
        self.assertEqual(audited[0]["event_type"], "DRAFT_UPDATED")
        self.assertEqual(db.commits, 1)

    def test_edit_is_blocked_when_quote_is_missing_or_risk_fails(self):
        req = ModifyDraftRequest(symbol="TCS.NS", side="BUY", order_type="MARKET", quantity=5)
        db = FakeDB()
        with self.assertRaises(HTTPException) as missing_quote:
            asyncio.run(modify_order_draft("order-1", req, request(None), db))
        self.assertEqual(missing_quote.exception.status_code, 409)
        self.assertEqual(db.rollbacks, 1)

        db = FakeDB()

        class Risk:
            def __init__(self, _db):
                pass

            async def check_order(self, _draft):
                return SimpleNamespace(passed=False, score=10, reason="limit exceeded")

        with patch("routers.orders.RiskBudgetEngine", Risk):
            with self.assertRaises(HTTPException) as risk_failure:
                asyncio.run(modify_order_draft("order-1", req, request(), db))
        self.assertEqual(risk_failure.exception.status_code, 422)
        self.assertFalse(any(sql.startswith("UPDATE orders SET") for sql, _ in db.calls))

    def test_cancel_marks_only_drafts_cancelled_and_audits(self):
        db = FakeDB()
        events = []

        class Audit:
            def __init__(self, _db):
                pass

            async def log(self, **kwargs):
                events.append(kwargs["event_type"])

        with patch("routers.orders.AuditLogger", Audit):
            response = asyncio.run(cancel_order_draft("order-1", db))
        cancel_sql = next(sql for sql, _ in db.calls)
        self.assertIn("status = 'DRAFT'", cancel_sql)
        self.assertEqual(response["success"], True)
        self.assertEqual(events, ["DRAFT_CANCELLED"])
        self.assertEqual(db.commits, 1)

        db = FakeDB(update_succeeds=False)
        with patch("routers.orders.AuditLogger", Audit):
            with self.assertRaises(HTTPException) as failure:
                asyncio.run(cancel_order_draft("order-1", db))
        self.assertEqual(failure.exception.status_code, 409)
        self.assertEqual(db.commits, 0)


if __name__ == "__main__":
    unittest.main()
