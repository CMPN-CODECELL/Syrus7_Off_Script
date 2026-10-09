import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

import main


class AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


class ReadinessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = AsyncMock()
        self.redis.ping.return_value = True
        self.redis.get.return_value = json.dumps({
            "prices": {"INFY.NS": 1823.4},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        self.db_session = AsyncMock()
        self.mock_response = MagicMock()
        self.mock_response.json.return_value = {"mode": "mock"}
        self.mock_response.raise_for_status = MagicMock()
        self.http = AsyncMock()
        self.http.get.return_value = self.mock_response

        self.patches = [
            patch.object(main, "redis_client", self.redis),
            patch.object(main, "AsyncSessionLocal", return_value=AsyncContext(self.db_session)),
            patch("main.httpx.AsyncClient", return_value=AsyncContext(self.http)),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    async def test_readiness_requires_all_dependencies_and_fresh_demo_quotes(self):
        result = await main.readiness()

        self.assertEqual(result["status"], "ready")
        self.assertEqual(set(result["checks"].values()), {"ok"})
        self.db_session.execute.assert_awaited_once()
        self.redis.ping.assert_awaited_once()

    async def test_stale_quote_snapshot_marks_backend_not_ready(self):
        self.redis.get.return_value = json.dumps({
            "prices": {"INFY.NS": 1823.4},
            "updated_at": "2020-01-01T00:00:00+00:00",
        })

        with self.assertRaises(HTTPException) as raised:
            await main.readiness()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["demo_quotes"], "down")

    async def test_malformed_snapshot_marks_backend_not_ready(self):
        self.redis.get.return_value = '["not", "a", "snapshot"]'

        with self.assertRaises(HTTPException) as raised:
            await main.readiness()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["demo_quotes"], "down")

    async def test_database_outage_marks_backend_not_ready(self):
        self.db_session.execute.side_effect = RuntimeError("database unavailable")

        with self.assertRaises(HTTPException) as raised:
            await main.readiness()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["postgres"], "down")

    async def test_redis_outage_marks_backend_not_ready(self):
        self.redis.ping.side_effect = RuntimeError("redis unavailable")

        with self.assertRaises(HTTPException) as raised:
            await main.readiness()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail["checks"]["redis"], "down")
        self.assertEqual(raised.exception.detail["checks"]["demo_quotes"], "down")


if __name__ == "__main__":
    unittest.main()
