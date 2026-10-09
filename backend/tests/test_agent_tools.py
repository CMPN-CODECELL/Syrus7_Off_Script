import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from agent.agent import TradingAgent


class AgentToolValidationTests(unittest.TestCase):
    def setUp(self):
        self.agent = TradingAgent()

    def run_tool(self, name, arguments):
        return asyncio.run(self.agent._call_tool(name, arguments))

    def test_unknown_symbol_is_rejected_without_creating_a_draft(self):
        result = json.loads(self.run_tool("create_order_draft", {
            "symbol": "FAKE.NS",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 1,
        }))
        self.assertIn("error", result)
        self.assertNotIn("draft", result)

    def test_invalid_market_quantity_is_rejected_before_quote_request(self):
        with patch("agent.agent.httpx.AsyncClient") as client_factory:
            client = AsyncMock()
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            client_factory.return_value = context

            result = json.loads(self.run_tool("create_order_draft", {
                "symbol": "INFY.NS",
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 0,
            }))

        self.assertIn("positive whole number", result["error"])
        self.assertNotIn("draft", result)
        client.get.assert_not_awaited()

    def test_order_plan_validates_all_legs_and_captures_quotes(self):
        with patch("agent.agent.httpx.AsyncClient") as client_factory:
            client = AsyncMock()
            response = MagicMock()
            response.json.return_value = {"ltp": 100.0}
            response.raise_for_status = MagicMock()
            client.get.return_value = response
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            client_factory.return_value = context

            result = json.loads(self.run_tool("create_order_plan", {"orders": [
                {"symbol": "INFY.NS", "side": "BUY", "order_type": "MARKET", "quantity": 2},
                {"symbol": "TCS.NS", "side": "SELL", "order_type": "MARKET", "quantity": 3},
            ]}))

        self.assertTrue(result["draft"])
        self.assertEqual(len(result["data"]["orders"]), 2)
        self.assertEqual([leg["quoted_price"] for leg in result["data"]["orders"]], [100.0, 100.0])
        self.assertEqual(client.get.await_count, 2)

    def test_order_plan_rejects_invalid_leg_without_returning_draft(self):
        result = json.loads(self.run_tool("create_order_plan", {"orders": [
            {"symbol": "INFY.NS", "side": "BUY", "order_type": "MARKET", "quantity": 0},
            {"symbol": "TCS.NS", "side": "SELL", "order_type": "MARKET", "quantity": 2},
        ]}))
        self.assertIn("positive whole-number", result["error"])
        self.assertNotIn("draft", result)

    def test_invalid_standing_trigger_is_rejected_without_activation(self):
        result = json.loads(self.run_tool("create_standing_instruction", {
            "name": "Unsupported percent rule",
            "symbol": "TCS.NS",
            "condition_type": "PERCENT_CHANGE",
            "condition_value": 5,
            "action_side": "SELL",
            "action_quantity": 1,
        }))
        self.assertIn("PRICE_ABOVE or PRICE_BELOW", result["error"])
        self.assertNotIn("draft", result)

    def test_risk_limit_proposal_enforces_hard_ceiling_before_confirmation(self):
        result = json.loads(self.run_tool("propose_risk_limit_update", {
            "limit_type": "MAX_ORDER_VALUE",
            "value": 50_000_001,
        }))
        self.assertIn("cannot exceed", result["error"])
        self.assertNotIn("draft", result)

    def test_daily_trade_report_uses_broker_data(self):
        with patch("agent.agent.httpx.AsyncClient") as client_factory:
            client = AsyncMock()
            response = MagicMock()
            response.json.return_value = {"mode": "demo", "total_orders": 0, "realized_pnl": None}
            response.raise_for_status = MagicMock()
            client.get.return_value = response
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            client_factory.return_value = context

            result = json.loads(self.run_tool("get_daily_trade_report", {}))

        self.assertEqual(result["mode"], "demo")
        self.assertIsNone(result["realized_pnl"])
        self.assertTrue(client.get.call_args.args[0].endswith("/reports/daily"))

    def test_broker_tool_failure_is_sanitized(self):
        with patch("agent.agent.httpx.AsyncClient") as client_factory:
            client = AsyncMock()
            client.get.side_effect = RuntimeError("private-hostname-and-query-details")
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=client)
            context.__aexit__ = AsyncMock(return_value=False)
            client_factory.return_value = context

            result = json.loads(self.run_tool("get_portfolio", {}))

        self.assertIn("could not complete", result["error"])
        self.assertNotIn("private-hostname", result["error"])


class GeminiToolRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_failure_returns_sanitized_sse_error(self):
        class FailingModels:
            async def generate_content(self, **kwargs):
                raise RuntimeError("private provider response details")

        agent = TradingAgent()
        agent.client = SimpleNamespace(aio=SimpleNamespace(models=FailingModels()))
        with patch("agent.agent.settings.gemini_api_key", "test-key"):
            events = [event async for event in agent.stream([{"role": "user", "content": "hello"}])]

        serialized = "".join(events)
        self.assertIn("Check the API key, model availability, or quota", serialized)
        self.assertNotIn("private provider response details", serialized)
        self.assertIn('"type": "done"', serialized)

    async def test_tool_round_trip_preserves_model_turn_and_call_id(self):
        call = SimpleNamespace(name="get_portfolio", args={}, id="call-123")
        model_turn = SimpleNamespace(
            role="model",
            thought_signature="opaque-thought-signature",
            parts=[SimpleNamespace(function_call=call, text=None)],
        )
        final_turn = SimpleNamespace(
            parts=[SimpleNamespace(function_call=None, text="Portfolio is demo data.")],
        )

        class FakeModels:
            def __init__(self):
                self.snapshots = []
                self.responses = [
                    SimpleNamespace(candidates=[SimpleNamespace(content=model_turn)]),
                    SimpleNamespace(candidates=[SimpleNamespace(content=final_turn)]),
                ]

            async def generate_content(self, *, model, contents, config):
                self.snapshots.append(list(contents))
                return self.responses.pop(0)

        models = FakeModels()
        agent = TradingAgent()
        agent.client = SimpleNamespace(aio=SimpleNamespace(models=models))
        with patch("agent.agent.settings.gemini_api_key", "test-key"), patch.object(
            agent, "_call_tool", new=AsyncMock(return_value=json.dumps({"total_value": 123}))
        ):
            events = [event async for event in agent.stream([{"role": "user", "content": "portfolio?"}])]

        second_request = models.snapshots[1]
        self.assertIn(model_turn, second_request)
        function_responses = [
            part.function_response
            for content in second_request
            for part in getattr(content, "parts", [])
            if getattr(part, "function_response", None)
        ]
        self.assertEqual(len(function_responses), 1)
        self.assertEqual(function_responses[0].id, "call-123")
        self.assertTrue(any('"type": "done"' in event for event in events))
        self.assertTrue(any("Portfolio is demo data." in event for event in events))

if __name__ == "__main__":
    unittest.main()
