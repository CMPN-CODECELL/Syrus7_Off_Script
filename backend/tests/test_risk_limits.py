import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException

from routers.risk_limits import approve_risk_limit_draft, persist_risk_limit_draft
from services.risk_engine import validate_limit_value


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


class FakeDB:
    def __init__(self, draft=None, current_value=Decimal("500000")):
        self.calls = []
        self.commits = 0
        self.draft = draft
        self.current_value = current_value

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))
        if sql.startswith("SELECT * FROM risk_limit_drafts"):
            return Result(row=self.draft)
        if sql.startswith("SELECT value_numeric FROM risk_limits"):
            return Result(row={"value_numeric": self.current_value} if self.current_value is not None else None)
        if sql.startswith("UPDATE risk_limit_drafts") and "RETURNING id" in sql:
            return Result(row={"id": params.get("id")})
        if sql.startswith("UPDATE risk_limits"):
            return Result(rows=[{"id": "risk-limit-id"}])
        return Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def sample_draft(status="DRAFT", expires_at=None):
    return {
        "id": "f78e2acd-efaf-4fb1-a290-faf4288ac334",
        "limit_type": "MAX_ORDER_VALUE",
        "old_value": Decimal("500000"),
        "new_value": Decimal("250000"),
        "status": status,
        "expires_at": expires_at or datetime.now(timezone.utc) + timedelta(minutes=1),
    }


class RiskLimitValidationTests(unittest.TestCase):
    def test_valid_cash_limit_is_preserved(self):
        self.assertEqual(validate_limit_value("MAX_ORDER_VALUE", 250_000), 250_000.0)

    def test_count_limits_require_whole_numbers(self):
        with self.assertRaisesRegex(ValueError, "whole number"):
            validate_limit_value("MAX_POSITION_SIZE", 12.5)

    def test_limits_reject_non_finite_or_non_positive_values(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_limit_value("MAX_ORDER_VALUE", value)

    def test_unsupported_daily_loss_limit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Choose MAX_ORDER_VALUE"):
            validate_limit_value("MAX_DAILY_LOSS", 100_000)

    def test_limits_enforce_demo_hard_ceiling(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            validate_limit_value("MAX_ORDERS_PER_DAY", 501)

    def test_unknown_limit_cannot_be_changed(self):
        with self.assertRaisesRegex(ValueError, "Choose MAX_ORDER_VALUE"):
            validate_limit_value("ARBITRARY_SETTING", 1)


class RiskLimitDraftTests(unittest.IsolatedAsyncioTestCase):
    async def test_proposal_is_persisted_without_changing_active_limit(self):
        db = FakeDB()

        draft = await persist_risk_limit_draft(db, "MAX_ORDER_VALUE", 250_000)

        self.assertEqual(draft["current_value"], 500_000.0)
        self.assertEqual(draft["value"], 250_000.0)
        self.assertTrue(any(sql.startswith("INSERT INTO risk_limit_drafts") for sql, _ in db.calls))
        self.assertFalse(any(sql.startswith("UPDATE risk_limits") for sql, _ in db.calls))
        self.assertEqual(db.commits, 1)

    async def test_explicit_approval_applies_and_audits_proposal_once(self):
        db = FakeDB(draft=sample_draft())

        response = await approve_risk_limit_draft(db.draft["id"], db)

        self.assertTrue(response["success"])
        self.assertEqual(response["value"], 250_000.0)
        self.assertTrue(any(sql.startswith("UPDATE risk_limits") for sql, _ in db.calls))
        self.assertTrue(any("RISK_LIMIT_UPDATED" in params.values() for sql, params in db.calls if "INSERT INTO audit_log" in sql))
        self.assertEqual(db.commits, 1)

    async def test_approved_proposal_retry_is_idempotent(self):
        db = FakeDB(draft=sample_draft(status="APPROVED"))

        response = await approve_risk_limit_draft(db.draft["id"], db)

        self.assertTrue(response["success"])
        self.assertTrue(response["already_applied"])
        self.assertFalse(any(sql.startswith("UPDATE risk_limits") for sql, _ in db.calls))

    async def test_expired_proposal_cannot_change_the_limit(self):
        db = FakeDB(draft=sample_draft(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))

        with self.assertRaises(HTTPException) as raised:
            await approve_risk_limit_draft(db.draft["id"], db)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertFalse(any(sql.startswith("UPDATE risk_limits") for sql, _ in db.calls))
        self.assertTrue(any("RISK_LIMIT_CHANGE_EXPIRED" in params.values() for sql, params in db.calls if "INSERT INTO audit_log" in sql))

    async def test_proposal_stales_if_active_limit_changed_after_preview(self):
        db = FakeDB(draft=sample_draft(), current_value=Decimal("400000"))

        with self.assertRaises(HTTPException) as raised:
            await approve_risk_limit_draft(db.draft["id"], db)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertFalse(any(sql.startswith("UPDATE risk_limits") for sql, _ in db.calls))
        self.assertTrue(any("SET status = 'STALE'" in sql for sql, _ in db.calls))


if __name__ == "__main__":
    unittest.main()
