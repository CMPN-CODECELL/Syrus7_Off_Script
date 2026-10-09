import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.price_poller import PricePoller


class FakePipeline:
    def __init__(self):
        self.values = {}

    def set(self, key, value, ex=None):
        self.values[key] = (value, ex)
        return self

    async def execute(self):
        return None


class FakeRedis:
    def __init__(self):
        self.pipe = FakePipeline()

    def pipeline(self):
        return self.pipe


class PricePollerTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_snapshot_uses_only_labeled_mock_quotes(self):
        redis = FakeRedis()
        poller = PricePoller(redis)
        symbols = {
            "RELIANCE.NS": 2905.5,
            "INFY.NS": 1823.4,
            "TCS.NS": 4215.75,
            "HDFCBANK.NS": 1698.2,
            "WIPRO.NS": 567.85,
            "SBIN.NS": 832.6,
        }
        responses = []
        for price in symbols.values():
            response = MagicMock()
            response.json.return_value = {"ltp": price, "market_data_source": "fixed_demo_fallback"}
            response.raise_for_status = MagicMock()
            responses.append(response)
        client = AsyncMock()
        client.get.side_effect = responses
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=client)
        context.__aexit__ = AsyncMock(return_value=False)

        with patch("services.price_poller.httpx.AsyncClient", return_value=context):
            await poller._fetch_and_cache()

        self.assertTrue(poller.first_snapshot.is_set())
        self.assertEqual(redis.pipe.values["price:RELIANCE.NS"][0], "2905.5")
        self.assertEqual(redis.pipe.values["price:INFY.NS"][0], "1823.4")
        snapshot = json.loads(redis.pipe.values["price:snapshot"][0])
        self.assertEqual(snapshot["sources"]["INFY.NS"], "fixed_demo_fallback")
        self.assertEqual(snapshot["prices"], symbols)
        self.assertEqual(client.get.await_count, 6)


if __name__ == "__main__":
    unittest.main()
