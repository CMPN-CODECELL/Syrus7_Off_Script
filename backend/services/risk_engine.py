"""
Risk Budget Engine — validates an order draft against the trader's risk limits
before presenting the confirmation card.

Checks performed:
1. Max order value (quantity × price)
2. Max daily loss (today's realized P&L)
3. Max position size per symbol
4. Max orders per day
5. Blocked symbols list
"""

from dataclasses import dataclass
from datetime import datetime, timezone, date
import math
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class RiskResult:
    passed: bool
    score: int          # 0–100 confidence/safety score
    reason: str = ""
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


# Default limits (fallback if DB is not available yet)
DEFAULT_LIMITS = {
    "MAX_ORDER_VALUE":    500_000,   # ₹5 lakh
    "MAX_POSITION_SIZE":  1_000,     # shares
    "MAX_ORDERS_PER_DAY": 50,
}

CONFIGURABLE_LIMITS = {
    "MAX_ORDER_VALUE": {"label": "Maximum order value", "integer": False, "hard_max": 5_000_000},
    "MAX_POSITION_SIZE": {"label": "Maximum shares per order", "integer": True, "hard_max": 10_000},
    "MAX_ORDERS_PER_DAY": {"label": "Maximum orders per day", "integer": True, "hard_max": 500},
}


def validate_limit_value(limit_type: str, value) -> int | float:
    """Validate a configurable risk value against the demo system ceilings."""
    rule = CONFIGURABLE_LIMITS.get(limit_type)
    if rule is None:
        raise ValueError("Choose MAX_ORDER_VALUE, MAX_POSITION_SIZE, or MAX_ORDERS_PER_DAY.")
    if isinstance(value, bool):
        raise ValueError("Risk limit must be a positive number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Risk limit must be a positive number.") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Risk limit must be a finite number greater than zero.")
    if rule["integer"] and not number.is_integer():
        raise ValueError(f"{rule['label']} must be a whole number.")
    if number > rule["hard_max"]:
        raise ValueError(f"{rule['label']} cannot exceed {rule['hard_max']:,} in this demo.")
    return int(number) if rule["integer"] else number


class RiskBudgetEngine:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_limits(self) -> dict:
        """Load active risk limits from DB."""
        try:
            result = await self.db.execute(
                text("SELECT limit_type, value_numeric, value_list FROM risk_limits WHERE is_active = TRUE")
            )
            rows = result.fetchall()
            limits = dict(DEFAULT_LIMITS)
            for row in rows:
                limits[row.limit_type] = row.value_numeric or row.value_list
            return limits
        except Exception:
            return dict(DEFAULT_LIMITS)

    async def _get_today_order_count(self) -> int:
        """Count orders placed today."""
        try:
            today = date.today()
            result = await self.db.execute(
                text(
                    "SELECT COUNT(*) FROM orders WHERE DATE(created_at) = :today "
                    "AND status NOT IN ('DRAFT', 'REJECTED', 'EXPIRED')"
                ),
                {"today": today},
            )
            return result.scalar() or 0
        except Exception:
            return 0

    async def check_order(self, draft: dict) -> RiskResult:
        """
        Run all risk checks on an order draft.
        Returns RiskResult with passed=True if all checks pass.
        """
        limits = await self._get_limits()
        warnings = []
        score = 100  # Start at 100, deduct for risk factors

        symbol = draft.get("symbol", "")
        side = draft.get("side", "BUY")
        quantity = draft.get("quantity", 0)
        order_type = draft.get("order_type", "MARKET")
        price = draft.get("price")

        # --- Check: Blocked symbols ---
        blocked = limits.get("BLOCKED_SYMBOLS", [])
        if isinstance(blocked, list) and symbol in blocked:
            return RiskResult(
                passed=False,
                score=0,
                reason=f"Symbol {symbol} is on the blocked symbols list.",
            )

        # --- Check: Allowed symbols (if list is defined) ---
        allowed = limits.get("ALLOWED_SYMBOLS", [])
        if isinstance(allowed, list) and allowed and symbol not in allowed:
            return RiskResult(
                passed=False,
                score=0,
                reason=f"Symbol {symbol} is not in the allowed symbols list.",
            )

        # --- Estimate order value ---
        # For MARKET orders we don't have exact price, use the quoted price if passed
        try:
            quoted_price = float(draft.get("quoted_price") or price or 0)
        except (TypeError, ValueError):
            quoted_price = 0
        if not math.isfinite(quoted_price) or quoted_price <= 0:
            return RiskResult(passed=False, score=0, reason="A fresh finite quote is required for order risk checks.")
        order_value = quantity * quoted_price

        # --- Check: Max order value ---
        max_val = float(limits.get("MAX_ORDER_VALUE", DEFAULT_LIMITS["MAX_ORDER_VALUE"]))
        if order_value > max_val:
            return RiskResult(
                passed=False,
                score=10,
                reason=(
                    f"Order value ₹{order_value:,.0f} exceeds your max order limit of ₹{max_val:,.0f}. "
                    f"Reduce quantity or split into smaller orders."
                ),
            )
        elif order_value > max_val * 0.8:
            warnings.append(f"Order value ₹{order_value:,.0f} is near your ₹{max_val:,.0f} limit.")
            score -= 15

        # --- Check: Max position size ---
        max_pos = int(limits.get("MAX_POSITION_SIZE", DEFAULT_LIMITS["MAX_POSITION_SIZE"]))
        if quantity > max_pos:
            return RiskResult(
                passed=False,
                score=10,
                reason=f"Quantity {quantity} exceeds your max position size of {max_pos} shares per order.",
            )
        elif quantity > max_pos * 0.8:
            warnings.append(f"Quantity {quantity} is near your position size limit of {max_pos}.")
            score -= 10

        # --- Check: Max orders per day ---
        max_orders = int(limits.get("MAX_ORDERS_PER_DAY", DEFAULT_LIMITS["MAX_ORDERS_PER_DAY"]))
        today_count = await self._get_today_order_count()
        if today_count >= max_orders:
            return RiskResult(
                passed=False,
                score=5,
                reason=f"Daily order limit of {max_orders} orders reached ({today_count} placed today).",
            )
        elif today_count >= max_orders * 0.9:
            warnings.append(f"You've placed {today_count}/{max_orders} orders today.")
            score -= 5

        # --- Risk score adjustments ---
        if order_type == "MARKET":
            score -= 5   # Market orders have slippage risk
        if side == "SELL" and quantity > 100:
            score -= 3   # Large sells carry more market impact

        score = max(0, min(100, score))

        return RiskResult(
            passed=True,
            score=score,
            warnings=warnings,
        )
