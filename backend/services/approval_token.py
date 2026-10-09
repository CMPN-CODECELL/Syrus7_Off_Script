"""
Approval Token Service — generates and validates hash-bound, single-use approval tokens.

A token is:
  - Bound to the EXACT order (symbol, side, qty, price, order_id)
  - Time-limited (default 60 seconds TTL)
  - Single-use (consumed on validation, cannot be reused)

This means: if the price changes, the old token is invalid for the new price.
And once used, it cannot be replayed.
"""

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

from config import settings


@dataclass
class TokenResult:
    valid: bool
    reason: str = ""


class ApprovalTokenService:

    @staticmethod
    def _canonical_number(value):
        """Make SQL Decimal and JSON numeric values compare consistently."""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return format(value.normalize(), "f")
        if isinstance(value, float):
            return format(Decimal(str(value)).normalize(), "f")
        return str(value)

    def generate(self, order_data: dict) -> tuple[str, float]:
        """
        Generate a signed approval token for an exact order.

        Returns:
            (token_str, expires_at_unix_timestamp)
        """
        expires_at = time.time() + settings.approval_token_ttl_seconds

        # Canonical payload — deterministic, includes all order-defining fields
        payload = {
            "order_id":    str(order_data.get("order_id", order_data.get("id", ""))),
            "symbol":      order_data["symbol"],
            "side":        order_data["side"],
            "order_type":  order_data["order_type"],
            "quantity":    order_data["quantity"],
            "price":       self._canonical_number(order_data.get("price")),
            "trigger_price": self._canonical_number(order_data.get("trigger_price")),
            "quoted_price": self._canonical_number(order_data.get("quoted_price")),
            "expires_at":  int(expires_at),
            "nonce":       str(uuid.uuid4()),   # uniqueness per generation
        }

        payload_str = json.dumps(payload, sort_keys=True)

        # HMAC-SHA256 signature
        signature = hmac.new(
            settings.approval_token_secret.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        token = f"{payload_str}::{signature}"

        return token, expires_at

    def validate(self, token: str, order_data: dict) -> TokenResult:
        """
        Validate a token against the order it was issued for.

        Checks:
        1. Signature is valid (not tampered)
        2. Token has not expired
        3. Token payload matches the order exactly
        """
        try:
            if "::" not in token:
                return TokenResult(valid=False, reason="Malformed token")

            payload_str, provided_sig = token.rsplit("::", 1)
            payload = json.loads(payload_str)

        except (ValueError, json.JSONDecodeError):
            return TokenResult(valid=False, reason="Token parse error")

        # 1. Verify signature
        expected_sig = hmac.new(
            settings.approval_token_secret.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, provided_sig):
            return TokenResult(valid=False, reason="Invalid token signature — possible tampering")

        # 2. Check expiry
        if time.time() > payload.get("expires_at", 0):
            return TokenResult(valid=False, reason="Token has expired")

        # 3. Check payload matches current order exactly
        mismatches = []
        checks = {
            "order_id": str(order_data.get("order_id", order_data.get("id", ""))),
            "symbol":   order_data.get("symbol", ""),
            "side":     order_data.get("side", ""),
            "order_type": order_data.get("order_type", ""),
            "quantity": order_data.get("quantity", 0),
            "price": self._canonical_number(order_data.get("price")),
            "trigger_price": self._canonical_number(order_data.get("trigger_price")),
            "quoted_price": self._canonical_number(order_data.get("quoted_price")),
        }

        for field, expected_value in checks.items():
            token_value = payload.get(field)
            if str(token_value) != str(expected_value):
                mismatches.append(f"{field}: token has '{token_value}', order has '{expected_value}'")

        if mismatches:
            return TokenResult(
                valid=False,
                reason=f"Token does not match order: {'; '.join(mismatches)}",
            )

        return TokenResult(valid=True)
