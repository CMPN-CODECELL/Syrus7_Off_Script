import unittest
import json
from decimal import Decimal
from unittest.mock import patch

from services.approval_token import ApprovalTokenService
from services.instruments import canonical_symbol


class ApprovalTokenTests(unittest.TestCase):
    def setUp(self):
        self.service = ApprovalTokenService()
        self.order = {
            "id": "00000000-0000-0000-0000-000000000001",
            "symbol": "INFY.NS",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 50,
            "price": None,
            "trigger_price": None,
            "quoted_price": Decimal("1821.3200"),
        }
        self.token, _ = self.service.generate(self.order)

    def test_token_accepts_exact_order(self):
        self.assertTrue(self.service.validate(self.token, self.order).valid)

    def test_token_rejects_changed_quantity(self):
        changed = {**self.order, "quantity": 51}
        self.assertFalse(self.service.validate(self.token, changed).valid)

    def test_token_rejects_changed_quote(self):
        changed = {**self.order, "quoted_price": Decimal("1821.33")}
        self.assertFalse(self.service.validate(self.token, changed).valid)

    def test_token_rejects_changed_order_type_and_limit_price(self):
        changed = {**self.order, "order_type": "LIMIT", "price": Decimal("1800")}
        self.assertFalse(self.service.validate(self.token, changed).valid)

    def test_token_rejects_expired_approval(self):
        payload, _ = self.token.rsplit("::", 1)
        expires_at = json.loads(payload)["expires_at"]
        with patch("services.approval_token.time.time", return_value=expires_at + 1):
            result = self.service.validate(self.token, self.order)
        self.assertFalse(result.valid)
        self.assertEqual(result.reason, "Token has expired")

    def test_token_rejects_modified_signature(self):
        payload, signature = self.token.rsplit("::", 1)
        tampered = f"{payload}::{signature[:-1]}{'0' if signature[-1] != '0' else '1'}"
        result = self.service.validate(tampered, self.order)
        self.assertFalse(result.valid)
        self.assertIn("Invalid token signature", result.reason)


class InstrumentTests(unittest.TestCase):
    def test_symbol_is_canonicalized(self):
        self.assertEqual(canonical_symbol(" infy.ns "), "INFY.NS")

    def test_unknown_symbol_is_rejected(self):
        with self.assertRaises(ValueError):
            canonical_symbol("FAKE.NS")


if __name__ == "__main__":
    unittest.main()
