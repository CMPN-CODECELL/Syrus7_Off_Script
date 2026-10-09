"""Gemini-powered trading copilot with broker tools."""

import json
import logging
import math
from typing import AsyncIterator, Optional

import httpx
from google import genai
from google.genai import types

from config import settings
from services.instruments import canonical_symbol

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are StockItUp, an AI trading copilot for the StockItUp demo.
You help traders manage their portfolio and place orders by understanding plain English requests.
Broker and account data may be simulated; identify it as demo data when appropriate.

CORE PRINCIPLES:
1. You NEVER place orders. You only create drafts. The trader always has the final say.
1a. If one request asks for multiple order legs (for example, several buys/sells or a basket), use create_order_plan once with every leg. Do not create separate order drafts for a multi-leg request. Explain that the trader approves the complete plan with one action.
2. Before creating any order draft, always fetch the latest quote to show the trader the current price.
3. When the trader's request is ambiguous, ask a clarifying question rather than guessing.
4. Be concise and precise — traders value speed. Give data, not fluff.
5. Always confirm the symbol exists in the instrument master before creating a draft.
6. Format numbers as Indian currency where relevant (₹ with lakh notation for large numbers).

Use only data returned by the configured broker/data service. Describe mock quotes as fixed demo data, not live market data. Never describe mock values as live. Risk-budget changes must be proposed with the risk-limit tool, clearly state current and proposed values, and wait for explicit approval before claiming the limit changed. For a daily or narrative trading report, call get_daily_trade_report and base every count and amount on its output. Do not estimate or invent realized P&L when it is unavailable."""

TOOL_DECLARATIONS = [
    {"name": "get_quote", "description": "Get a quote from the configured broker data service. In mock mode, quote values are simulated. Supported symbols: RELIANCE.NS, INFY.NS, TCS.NS, HDFCBANK.NS, WIPRO.NS, SBIN.NS.", "parameters": {"type": "OBJECT", "properties": {"symbol": {"type": "STRING", "description": "Supported NSE stock symbol"}}, "required": ["symbol"]}},
    {"name": "get_portfolio", "description": "Get account summary: funds, portfolio value", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_positions", "description": "Get open positions with P&L", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_order_history", "description": "Get order history", "parameters": {"type": "OBJECT", "properties": {"status": {"type": "STRING", "description": "ALL, FILLED, PARTIAL, REJECTED, CANCELLED"}}}},
    {"name": "get_daily_trade_report", "description": "Get a factual summary of today's demo orders, fills, sides, turnover, rejections, and pending orders for the narrative trade report. Do not infer realized P&L; it is unavailable in the demo ledger.", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "search_instrument", "description": "Search for valid stock symbols", "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING", "description": "Search term"}}, "required": ["query"]}},
    {"name": "create_order_draft", "description": "Create order draft for trader approval. NEVER place orders directly.", "parameters": {"type": "OBJECT", "properties": {"symbol": {"type": "STRING"}, "side": {"type": "STRING", "description": "BUY or SELL"}, "order_type": {"type": "STRING", "description": "MARKET, LIMIT, SL, SL-M"}, "quantity": {"type": "INTEGER"}, "price": {"type": "NUMBER", "description": "For LIMIT orders"}, "trigger_price": {"type": "NUMBER", "description": "For SL orders"}, "rationale": {"type": "STRING"}}, "required": ["symbol", "side", "order_type", "quantity"]}},
    {"name": "create_order_plan", "description": "Create one grouped plan containing 2-10 related orders requested together by the trader. Each leg remains a draft until the trader approves the entire plan once. Never execute orders.", "parameters": {"type": "OBJECT", "properties": {"orders": {"type": "ARRAY", "minItems": 2, "maxItems": 10, "items": {"type": "OBJECT", "properties": {"symbol": {"type": "STRING"}, "side": {"type": "STRING"}, "order_type": {"type": "STRING"}, "quantity": {"type": "INTEGER"}, "price": {"type": "NUMBER"}, "trigger_price": {"type": "NUMBER"}}, "required": ["symbol", "side", "order_type", "quantity"]}}}, "required": ["orders"]}},
    {"name": "create_standing_instruction", "description": "Propose a standing instruction with a price-above or price-below trigger. It must be explicitly activated by the trader.", "parameters": {"type": "OBJECT", "properties": {"name": {"type": "STRING"}, "symbol": {"type": "STRING"}, "condition_type": {"type": "STRING", "description": "PRICE_ABOVE or PRICE_BELOW"}, "condition_value": {"type": "NUMBER"}, "action_side": {"type": "STRING", "description": "BUY or SELL"}, "action_quantity": {"type": "INTEGER"}, "action_order_type": {"type": "STRING", "description": "MARKET only"}, "expires_in_hours": {"type": "NUMBER"}}, "required": ["name", "symbol", "condition_type", "condition_value", "action_side", "action_quantity"]}},
    {"name": "propose_risk_limit_update", "description": "Propose changing a configurable risk budget. Supported limits are MAX_ORDER_VALUE, MAX_POSITION_SIZE, and MAX_ORDERS_PER_DAY. Always show the current and proposed values and wait for explicit user approval before applying it.", "parameters": {"type": "OBJECT", "properties": {"limit_type": {"type": "STRING", "description": "MAX_ORDER_VALUE, MAX_POSITION_SIZE, or MAX_ORDERS_PER_DAY"}, "value": {"type": "NUMBER", "description": "New positive limit value"}}, "required": ["limit_type", "value"]}},
]

class TradingAgent:
    def __init__(self):
        self.client = None
        self.model = settings.gemini_model
        self.broker_url = settings.mock_api_url
        declarations = [types.FunctionDeclaration(**declaration) for declaration in TOOL_DECLARATIONS]
        self.model_config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=declarations)],
        )

    async def _call_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a broker tool and return its result as JSON."""
        async with httpx.AsyncClient(timeout=10.0) as http:
            try:
                if tool_name == "get_quote":
                    symbol = canonical_symbol(str(tool_input.get("symbol", "")))
                    r = await http.get(f"{self.broker_url}/quote/{symbol}")
                elif tool_name == "get_portfolio":
                    r = await http.get(f"{self.broker_url}/account")
                elif tool_name == "get_positions":
                    r = await http.get(f"{self.broker_url}/positions")
                elif tool_name == "get_order_history":
                    r = await http.get(f"{self.broker_url}/orders", params={"status": tool_input.get("status", "ALL")})
                elif tool_name == "get_daily_trade_report":
                    r = await http.get(f"{self.broker_url}/reports/daily")
                elif tool_name == "search_instrument":
                    r = await http.get(f"{self.broker_url}/instruments", params={"search": tool_input["query"]})
                elif tool_name == "create_order_draft":
                    symbol = canonical_symbol(str(tool_input.get("symbol", "")))
                    side = str(tool_input.get("side", "")).upper()
                    order_type = str(tool_input.get("order_type", "")).upper()
                    quantity = tool_input.get("quantity")
                    if side not in {"BUY", "SELL"}:
                        return json.dumps({"error": "Order side must be BUY or SELL."})
                    if order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
                        return json.dumps({"error": "Order type must be MARKET, LIMIT, SL, or SL-M."})
                    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
                        return json.dumps({"error": "Order quantity must be a positive whole number."})
                    try:
                        price = float(tool_input.get("price") or 0)
                        trigger_price = float(tool_input.get("trigger_price") or 0)
                    except (TypeError, ValueError):
                        return json.dumps({"error": "Order prices must be valid numbers."})
                    if order_type == "LIMIT" and (not math.isfinite(price) or price <= 0):
                        return json.dumps({"error": "A LIMIT order requires a positive limit price."})
                    if order_type in {"SL", "SL-M"} and (not math.isfinite(trigger_price) or trigger_price <= 0):
                        return json.dumps({"error": "A stop order requires a positive trigger price."})
                    tool_input.update({"symbol": symbol, "side": side, "order_type": order_type})

                    # Always attach a fresh quote before saving an order draft.
                    quote_response = await http.get(f"{self.broker_url}/quote/{symbol}")
                    quote_response.raise_for_status()
                    quote = quote_response.json()
                    quoted_price = float(quote.get("ltp") or 0)
                    if quoted_price <= 0:
                        return json.dumps({"error": f"No valid quote is available for {symbol}; no draft was created."})

                    tool_input["quoted_price"] = quoted_price
                    return json.dumps({"draft": True, "data": tool_input, "tool": tool_name})
                elif tool_name == "create_order_plan":
                    orders = tool_input.get("orders")
                    if not isinstance(orders, list) or not 2 <= len(orders) <= 10:
                        return json.dumps({"error": "An order plan must contain between 2 and 10 orders."})
                    validated = []
                    for raw in orders:
                        if not isinstance(raw, dict):
                            return json.dumps({"error": "Each plan leg must be an order object."})
                        symbol = canonical_symbol(str(raw.get("symbol", "")))
                        side, order_type = str(raw.get("side", "")).upper(), str(raw.get("order_type", "")).upper()
                        quantity = raw.get("quantity")
                        if side not in {"BUY", "SELL"} or order_type not in {"MARKET", "LIMIT", "SL", "SL-M"}:
                            return json.dumps({"error": "Every plan leg needs a valid side and order type."})
                        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 < quantity <= 10000:
                            return json.dumps({"error": "Every plan leg needs a positive whole-number quantity."})
                        price = float(raw.get("price") or 0)
                        trigger = float(raw.get("trigger_price") or 0)
                        if order_type == "LIMIT" and (not math.isfinite(price) or price <= 0):
                            return json.dumps({"error": f"{symbol} LIMIT order requires a positive price."})
                        if order_type in {"SL", "SL-M"} and (not math.isfinite(trigger) or trigger <= 0):
                            return json.dumps({"error": f"{symbol} stop order requires a positive trigger price."})
                        quote_response = await http.get(f"{self.broker_url}/quote/{symbol}")
                        quote_response.raise_for_status()
                        quoted = float(quote_response.json().get("ltp") or 0)
                        if not math.isfinite(quoted) or quoted <= 0:
                            return json.dumps({"error": f"No valid quote for {symbol}; no plan was created."})
                        validated.append({"symbol": symbol, "side": side, "order_type": order_type, "quantity": quantity,
                            "price": price if order_type == "LIMIT" else None,
                            "trigger_price": trigger if order_type in {"SL", "SL-M"} else None, "quoted_price": quoted})
                    return json.dumps({"draft": True, "data": {"orders": validated}, "tool": tool_name})
                elif tool_name == "create_standing_instruction":
                    symbol = canonical_symbol(str(tool_input.get("symbol", "")))
                    condition_type = str(tool_input.get("condition_type", "")).upper()
                    side = str(tool_input.get("action_side", "")).upper()
                    order_type = str(tool_input.get("action_order_type", "MARKET")).upper()
                    quantity = tool_input.get("action_quantity")
                    try:
                        condition_value = float(tool_input.get("condition_value"))
                    except (TypeError, ValueError):
                        return json.dumps({"error": "The trigger price must be a positive number."})
                    if condition_type not in {"PRICE_ABOVE", "PRICE_BELOW"}:
                        return json.dumps({"error": "Trigger type must be PRICE_ABOVE or PRICE_BELOW."})
                    if side not in {"BUY", "SELL"} or order_type != "MARKET":
                        return json.dumps({"error": "Standing instructions currently support BUY or SELL market orders only."})
                    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 < quantity <= 1000:
                        return json.dumps({"error": "Instruction quantity must be a whole number from 1 to 1000."})
                    if not math.isfinite(condition_value) or condition_value <= 0:
                        return json.dumps({"error": "The trigger price must be a positive number."})
                    expires = tool_input.get("expires_in_hours")
                    if expires is not None:
                        try:
                            expires = float(expires)
                        except (TypeError, ValueError):
                            return json.dumps({"error": "Instruction duration must be between 0 and 720 hours."})
                        if not math.isfinite(expires) or not 0 < expires <= 720:
                            return json.dumps({"error": "Instruction duration must be between 0 and 720 hours."})
                        tool_input["expires_in_hours"] = expires
                    tool_input.update({
                        "symbol": symbol,
                        "condition_type": condition_type,
                        "condition_value": condition_value,
                        "action_side": side,
                        "action_order_type": order_type,
                    })
                    return json.dumps({"draft": True, "data": tool_input, "tool": tool_name})
                elif tool_name == "propose_risk_limit_update":
                    from services.risk_engine import validate_limit_value

                    limit_type = str(tool_input.get("limit_type", "")).upper()
                    try:
                        value = validate_limit_value(limit_type, tool_input.get("value"))
                    except (TypeError, ValueError) as error:
                        return json.dumps({"error": str(error)})
                    tool_input.update({"limit_type": limit_type, "value": value})
                    return json.dumps({"draft": True, "data": tool_input, "tool": tool_name})
                else:
                    return json.dumps({"error": f"Unknown tool: {tool_name}"})
                r.raise_for_status()
                return json.dumps(r.json())
            except Exception:
                logger.exception("Broker tool request failed (%s)", tool_name)
                return json.dumps({"error": "The broker/data service could not complete this request. Check service health and retry."})

    async def stream(self, messages: list[dict], on_draft: Optional[callable] = None) -> AsyncIterator[str]:
        """Run Gemini function calls and stream the final response as SSE chunks."""
        if not settings.gemini_api_key:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Gemini is not configured. Add GEMINI_API_KEY to .env.local and restart the backend.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        if self.client is None:
            self.client = genai.Client(api_key=settings.gemini_api_key)

        contents = [
            types.Content(role="user" if msg["role"] == "user" else "model", parts=[types.Part(text=msg["content"])])
            for msg in messages[:-1]
            if msg.get("role") in ("user", "assistant") and isinstance(msg.get("content"), str) and msg["content"]
        ]
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=messages[-1]["content"] if messages else "")],
        ))

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=self.model_config,
            )

            for _ in range(10):
                candidate = response.candidates[0] if response.candidates else None
                parts = candidate.content.parts if candidate and candidate.content else []
                calls = [part.function_call for part in parts if part.function_call]
                for part in parts:
                    if part.text:
                        for i in range(0, len(part.text), 50):
                            yield f"data: {json.dumps({'type': 'text', 'content': part.text[i:i + 50]})}\n\n"

                if not calls:
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

                # Preserve the full model turn, including Gemini's thought signatures.
                contents.append(candidate.content)
                function_responses = []
                for call in calls:
                    args = dict(call.args or {})
                    yield f"data: {json.dumps({'type': 'tool_call', 'tool': call.name, 'input': args})}\n\n"
                    result_data = json.loads(await self._call_tool(call.name, args))
                    if result_data.get("error"):
                        yield f"data: {json.dumps({'type': 'error', 'content': str(result_data['error'])})}\n\n"
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return
                    if result_data.get("draft"):
                        draft_data = result_data.get("data", args)
                        if on_draft:
                            await on_draft(call.name, draft_data)
                        if call.name == "propose_risk_limit_update":
                            draft_data = result_data["data"] = draft_data
                        yield f"data: {json.dumps({'type': 'draft', 'tool': call.name, 'data': draft_data})}\n\n"
                    function_responses.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=call.name,
                            response={"result": result_data},
                            id=call.id,
                        )
                    ))
                contents.append(types.Content(role="user", parts=function_responses))
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=self.model_config,
                )

            yield f"data: {json.dumps({'type': 'error', 'content': 'Gemini reached the tool-call limit for this request.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception:
            logger.exception("Gemini chat request failed")
            yield f"data: {json.dumps({'type': 'error', 'content': 'Gemini could not complete this request. Check the API key, model availability, or quota, then retry. No broker order was submitted.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
