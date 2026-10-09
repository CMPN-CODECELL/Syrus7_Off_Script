import asyncio
import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from services.approval_token import ApprovalTokenService
from services.executor import ExecutorService


class Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def fetchone(self):
        return self.row


class FakeDB:
    def __init__(self, order):
        self.order = order
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append((sql, parameters or {}))
        if sql.strip().startswith("SELECT * FROM orders"):
            return Result(self.order)
        if "UPDATE orders SET status = 'SUBMITTED'" in sql:
            return Result({"id": self.order["id"]})
        return Result()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def approved_order():
    data = {
        "id": "00000000-0000-0000-0000-000000000051",
        "client_order_id": "SAFETY-TEST-051",
        "symbol": "INFY.NS",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 2,
        "price": None,
        "trigger_price": None,
        "quoted_price": Decimal("1823.40"),
        "status": "APPROVED",
    }
    token, _ = ApprovalTokenService().generate(data)
    data["approval_token"] = token
    return data, token


class ExecutorSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_approval_requests_submit_only_once(self):
        order, token = approved_order()
        post_calls = []

        class RacingDB(FakeDB):
            def __init__(self, initial_order):
                super().__init__(initial_order.copy())
                self.status = "APPROVED"

            async def execute(self, statement, parameters=None):
                sql = str(statement)
                self.statements.append((sql, parameters or {}))
                if sql.strip().startswith("SELECT * FROM orders"):
                    snapshot = self.order.copy()
                    snapshot["status"] = self.status
                    return Result(snapshot)
                if "UPDATE orders SET status = 'SUBMITTED'" in sql:
                    if self.status != "APPROVED":
                        return Result()
                    self.status = "SUBMITTED"
                    return Result({"id": self.order["id"]})
                if "status = :status" in sql and "filled_at" in sql:
                    self.status = (parameters or {})["status"]
                return Result()

        class Response:
            def __init__(self, body):
                self.body = body

            def json(self):
                return self.body

            def raise_for_status(self):
                return None

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, _url):
                await asyncio.sleep(0)
                return Response({"ltp": 1823.4})

            async def post(self, _url, json):
                post_calls.append(json)
                await asyncio.sleep(0)
                return Response({
                    "status": "FILLED", "filled_quantity": 2,
                    "average_price": 1823.4, "exchange_order_id": "MOCK-ONCE",
                })

        db = RacingDB(order)
        with patch("services.executor.httpx.AsyncClient", side_effect=lambda **_kwargs: Client()):
            results = await asyncio.gather(
                ExecutorService(db).execute(order["id"], token),
                ExecutorService(db).execute(order["id"], token),
            )

        self.assertEqual(len(post_calls), 1)
        self.assertEqual(sum(result.status == "FILLED" for result in results), 1)
        self.assertEqual(db.status, "FILLED")

    async def test_fill_status_uses_boolean_flag_and_persists_result(self):
        order, token = approved_order()
        db = FakeDB(order)
        quote_response = MagicMock()
        quote_response.json.return_value = {"ltp": 1823.4}
        quote_response.raise_for_status = MagicMock()
        order_response = MagicMock()
        order_response.json.return_value = {
            "status": "FILLED",
            "filled_quantity": 2,
            "average_price": 1823.4,
            "exchange_order_id": "MOCK-ORDER-1",
        }
        order_response.raise_for_status = MagicMock()

        clients = []
        for response in (quote_response, order_response):
            client = AsyncMock()
            client.get.return_value = response
            client.post.return_value = response
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            clients.append(context)

        with patch("services.executor.httpx.AsyncClient", side_effect=clients):
            result = await ExecutorService(db).execute(order["id"], token)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "FILLED")
        final_update = next(
            params for sql, params in db.statements
            if "filled_at = CASE WHEN :is_filled" in sql
        )
        self.assertIs(final_update["is_filled"], True)
        clients[1].__aenter__.return_value.post.assert_awaited_once()

    async def test_wrong_approval_token_never_reaches_broker(self):
        order, _ = approved_order()
        db = FakeDB(order)
        with patch("services.executor.httpx.AsyncClient") as client_factory:
            result = await ExecutorService(db).execute(order["id"], "wrong-token")

        self.assertFalse(result.success)
        self.assertEqual(result.status, "FAILED")
        client_factory.assert_not_called()
        self.assertTrue(any("TOKEN_REJECTED" in sql for sql, _ in db.statements))

    async def test_price_drift_stops_before_order_submission(self):
        order, token = approved_order()
        db = FakeDB(order)
        response = MagicMock()
        response.json.return_value = {"ltp": 1840.0}
        response.raise_for_status = MagicMock()
        client = AsyncMock()
        client.get.return_value = response
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        with patch("services.executor.httpx.AsyncClient", return_value=context):
            result = await ExecutorService(db).execute(order["id"], token)

        self.assertFalse(result.success)
        self.assertEqual(result.status, "PRICE_DRIFTED")
        client.get.assert_awaited_once()
        client.post.assert_not_awaited()
        self.assertTrue(any("SET status = 'DRAFT'" in sql for sql, _ in db.statements))


if __name__ == "__main__":
    unittest.main()
