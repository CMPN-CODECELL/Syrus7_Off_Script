import asyncio
import json
import unittest
from uuid import UUID

from services.audit_logger import AuditLogger


class RecordingDB:
    def __init__(self):
        self.statement = None
        self.parameters = None
        self.committed = False

    async def execute(self, statement, parameters):
        self.statement = str(statement)
        self.parameters = parameters

    async def commit(self):
        self.committed = True


class AuditLoggerTests(unittest.TestCase):
    def test_event_and_json_payload_are_inserted_without_implicit_commit(self):
        db = RecordingDB()
        order_id = UUID("00000000-0000-0000-0000-000000000001")
        asyncio.run(AuditLogger(db).log(
            event_type="DRAFT_CREATED",
            order_id=order_id,
            actor="SYSTEM",
            payload={"symbol": "INFY.NS", "quantity": 2},
            ip_address="127.0.0.1",
        ))

        self.assertIn("INSERT INTO audit_log", db.statement)
        self.assertIn("CAST(:payload AS jsonb)", db.statement)
        self.assertEqual(db.parameters["event_type"], "DRAFT_CREATED")
        self.assertEqual(db.parameters["order_id"], str(order_id))
        self.assertEqual(json.loads(db.parameters["payload"]), {"symbol": "INFY.NS", "quantity": 2})
        self.assertEqual(db.parameters["ip"], "127.0.0.1")
        self.assertFalse(db.committed)


if __name__ == "__main__":
    unittest.main()
