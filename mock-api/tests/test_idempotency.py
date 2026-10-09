import json
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import main


class MemoryRedis:
    def __init__(self):
        self.values = {}
        self.sets = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    async def smembers(self, key):
        return self.sets.get(key, set())

    async def mget(self, keys):
        return [self.values.get(key) for key in keys]


class MockOrderIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_redis = main.redis_client
        self.old_orders = main.MOCK_ORDERS.copy()
        self.redis = MemoryRedis()
        main.redis_client = self.redis
        main.MOCK_ORDERS.clear()

    async def asyncTearDown(self):
        main.redis_client = self.old_redis
        main.MOCK_ORDERS.clear()
        main.MOCK_ORDERS.update(self.old_orders)

    async def test_repeated_client_order_id_returns_same_order(self):
        request = main.PlaceOrderRequest(
            client_order_id="TEST-IDEMPOTENCY-001",
            symbol="INFY.NS",
            side="BUY",
            order_type="MARKET",
            quantity=1,
        )
        with patch.object(main, "get_mock_price", new=AsyncMock(return_value=1820.0)), patch.object(
            main.random, "choices", return_value=["FILLED"]
        ) as choose_fill:
            first = await main.place_order(request)
            second = await main.place_order(request)

        self.assertEqual(first["order_id"], second["order_id"])
        self.assertEqual(first["client_order_id"], "TEST-IDEMPOTENCY-001")
        self.assertEqual(json.loads(self.redis.values[main.client_order_key("TEST-IDEMPOTENCY-001")])["order_id"], first["order_id"])
        reconciled = await main.get_order_by_client_id("TEST-IDEMPOTENCY-001")
        self.assertEqual(reconciled["order_id"], first["order_id"])
        choose_fill.assert_called_once_with(["FILLED", "REJECTED"], weights=[95, 5])

    async def test_daily_report_counts_only_today_and_never_invents_pnl(self):
        today = main.datetime.now(main.timezone.utc).date()
        current = main.datetime.combine(today, main.datetime.min.time(), tzinfo=main.timezone.utc).isoformat()
        previous = main.datetime.combine(today - timedelta(days=1), main.datetime.min.time(), tzinfo=main.timezone.utc).isoformat()
        india_morning = main.datetime.combine(today - timedelta(days=1), main.datetime.min.time().replace(hour=20), tzinfo=main.timezone.utc).isoformat()
        report = main.build_daily_trade_report([
            {"created_at": current, "status": "FILLED", "side": "BUY", "symbol": "INFY.NS", "order_type": "MARKET", "quantity": 4, "filled_quantity": 4, "average_price": 100.0},
            {"created_at": india_morning, "status": "FILLED", "side": "BUY", "symbol": "TCS.NS", "order_type": "MARKET", "quantity": 2, "filled_quantity": 2, "average_price": 100.0},
            {"created_at": current, "status": "REJECTED", "side": "SELL", "symbol": "TCS.NS", "order_type": "MARKET", "quantity": 2, "filled_quantity": 0, "average_price": None},
            {"created_at": previous, "status": "FILLED", "side": "BUY", "symbol": "SBIN.NS", "order_type": "MARKET", "quantity": 1, "filled_quantity": 1, "average_price": 50.0},
        ], today=today)

        self.assertEqual(report["total_orders"], 3)
        self.assertEqual(report["filled_orders"], 2)
        self.assertEqual(report["buy_orders"], 2)
        self.assertEqual(report["filled_shares"], 6)
        self.assertEqual(report["filled_turnover"], 600.0)
        self.assertEqual(report["rejected_orders"], 1)
        self.assertIsNone(report["realized_pnl"])

    async def test_unknown_instrument_is_rejected(self):
        with self.assertRaises(ValueError):
            main.PlaceOrderRequest(
                client_order_id="TEST-INVALID-001",
                symbol="FAKE.NS",
                side="BUY",
                order_type="MARKET",
                quantity=1,
            )

    async def test_client_id_cannot_be_reused_for_a_different_order(self):
        client_order_id = "TEST-IDEMPOTENCY-MISMATCH"
        self.redis.values[main.client_order_key(client_order_id)] = json.dumps({
            "client_order_id": client_order_id,
            "symbol": "INFY.NS",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 1,
            "price": None,
            "trigger_price": None,
            "status": "FILLED",
        })
        request = main.PlaceOrderRequest(
            client_order_id=client_order_id,
            symbol="INFY.NS",
            side="BUY",
            order_type="MARKET",
            quantity=2,
        )

        with self.assertRaises(main.HTTPException) as raised:
            await main.place_order(request)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("different order intent", raised.exception.detail)

    async def test_filled_orders_update_persistent_portfolio_projection(self):
        client_order_id = "TEST-PORTFOLIO-BUY"
        self.redis.sets["mock:order_ids"] = {client_order_id}
        self.redis.values[main.client_order_key(client_order_id)] = json.dumps({
            "client_order_id": client_order_id,
            "symbol": "INFY.NS",
            "side": "BUY",
            "status": "FILLED",
            "filled_quantity": 2,
            "average_price": 1823.89,
            "created_at": "2026-10-09T12:00:00+00:00",
        })

        funds_available, positions = await main.get_portfolio_snapshot()

        self.assertEqual(positions["INFY.NS"]["quantity"], 102)
        self.assertAlmostEqual(funds_available, 2_500_000 - (2 * 1823.89))

    async def test_rejected_orders_do_not_change_portfolio(self):
        client_order_id = "TEST-PORTFOLIO-REJECT"
        self.redis.sets["mock:order_ids"] = {client_order_id}
        self.redis.values[main.client_order_key(client_order_id)] = json.dumps({
            "client_order_id": client_order_id,
            "symbol": "INFY.NS",
            "side": "BUY",
            "status": "REJECTED",
            "filled_quantity": 0,
            "average_price": None,
            "created_at": "2026-10-09T12:00:00+00:00",
        })

        funds_available, positions = await main.get_portfolio_snapshot()

        self.assertEqual(funds_available, main.MOCK_PORTFOLIO["funds_available"])
        self.assertEqual(positions["INFY.NS"]["quantity"], 100)

    async def test_fallback_only_quote_does_not_reuse_cached_price(self):
        self.redis.values["price:INFY.NS"] = "999.0"

        quote = await main.get_quote("INFY.NS", fallback_only=True)

        self.assertEqual(quote["ltp"], 1823.4)
        self.assertEqual(quote["market_data_source"], "fixed_demo_fallback")

    async def test_unimplemented_live_mode_fails_startup_instead_of_falling_back(self):
        with patch.object(main, "USE_REAL_API", True):
            with self.assertRaisesRegex(RuntimeError, "Live 021 trading is not integrated"):
                await main.startup()


if __name__ == "__main__":
    unittest.main()
