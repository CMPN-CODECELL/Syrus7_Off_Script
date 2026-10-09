import asyncio
import unittest

from services.risk_engine import RiskBudgetEngine


class Result:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or []
        self.value = scalar

    def fetchall(self):
        return self.rows

    def scalar(self):
        return self.value


class FakeDB:
    def __init__(self, max_order_value=500_000):
        self.max_order_value = max_order_value

    async def execute(self, statement, _params=None):
        sql = str(statement)
        if "SELECT limit_type, value_numeric, value_list FROM risk_limits" in sql:
            return Result(rows=[
                type("Row", (), {"limit_type": "MAX_ORDER_VALUE", "value_numeric": self.max_order_value, "value_list": None})()
            ])
        if "SELECT COUNT(*) FROM orders" in sql:
            return Result(scalar=0)
        return Result()


class RiskBudgetEnforcementTests(unittest.TestCase):
    def test_configured_order_value_is_enforced(self):
        engine = RiskBudgetEngine(FakeDB(max_order_value=50_000))
        result = asyncio.run(engine.check_order({
            "symbol": "INFY.NS", "side": "BUY", "order_type": "MARKET",
            "quantity": 100, "quoted_price": 1_000,
        }))
        self.assertFalse(result.passed)
        self.assertIn("exceeds your max order limit", result.reason)

    def test_missing_nonfinite_or_nonpositive_quote_fails_closed(self):
        for quote in (None, 0, -1, float("nan"), float("inf"), "not-a-price"):
            with self.subTest(quote=quote):
                result = asyncio.run(RiskBudgetEngine(FakeDB()).check_order({
                    "symbol": "INFY.NS", "side": "BUY", "order_type": "MARKET",
                    "quantity": 1, "quoted_price": quote,
                }))
                self.assertFalse(result.passed)
                self.assertIn("finite quote is required", result.reason)


if __name__ == "__main__":
    unittest.main()
