import json
import os
from unittest.mock import patch

import uuid

from psycopg2 import IntegrityError

from odoo.tests import tagged

from odoo.addons.elmogps_odoo.services.integration_contract import (
    TEST_SECRET,
    canonical_json_dumps,
    sign_body,
)
from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestElmogpsOutbox(ElmogpsTestCommon):

    def test_event_created_on_customer_activation(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Activation Test Partner",
                "is_elmogps_customer": True,
            }
        )
        before = self.env["elmogps.integration.event"].search_count(
            [("event_type", "=", "customer.activated"), ("model_name", "=", "res.partner"), ("record_id", "=", partner.id)]
        )
        partner.action_activate_elmogps_customer()
        after = self.env["elmogps.integration.event"].search_count(
            [("event_type", "=", "customer.activated"), ("model_name", "=", "res.partner"), ("record_id", "=", partner.id)]
        )
        self.assertEqual(after, before + 1)

    def test_duplicate_event_id_rejected(self):
        event_id = str(uuid.uuid4())
        self.env["elmogps.integration.event"].create(
            {
                "event_id": event_id,
                "event_type": "customer.updated",
                "payload": '{"test": true}',
            }
        )
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self.env["elmogps.integration.event"].create(
                    {
                        "event_id": event_id,
                        "event_type": "customer.updated",
                        "payload": '{"test": true}',
                    }
                )

    def test_hmac_signing(self):
        signer = self.env["elmogps.webhook.signer"]
        with patch.dict("os.environ", {"ELMOGPS_ODOO_WEBHOOK_SECRET": TEST_SECRET}):
            sig = signer.sign("1234567890", '{"a":1}', secret=TEST_SECRET)
        self.assertTrue(sig.startswith("sha256="))
        self.assertEqual(
            sig,
            sign_body("1234567890", '{"a":1}', TEST_SECRET),
        )

    def test_hmac_contract_test_vector(self):
        module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        vector_path = os.path.join(
            module_root,
            "docs/integration-contract/v1/test-vectors/hmac-sha256.json",
        )
        with open(vector_path, encoding="utf-8") as handle:
            vector = json.load(handle)
        signature = sign_body(vector["timestamp"], vector["raw_body"], vector["test_secret"])
        self.assertEqual(signature, vector["expected_signature"])

    def test_disabled_integration_skips_send(self):
        self.env.company.elmogps_integration_enabled = False
        event = self.env["elmogps.integration.event"].create(
            {
                "event_type": "customer.updated",
                "payload": '{"event_type":"customer.updated"}',
            }
        )
        success, status, msg, _retry = self.env["elmogps.webhook.client"].send_event(event)
        self.assertFalse(success)

    @patch("odoo.addons.elmogps_odoo.services.webhook_client.requests.post")
    def test_http_failure_retries(self, mock_post):
        mock_post.side_effect = Exception("connection failed")
        self.env.company.write(
            {
                "elmogps_integration_enabled": True,
                "elmogps_api_base_url": "https://example.test",
                "elmogps_webhook_max_attempts": 3,
            }
        )
        event = self.env["elmogps.integration.event"].create(
            {
                "event_type": "customer.updated",
                "payload": canonical_json_dumps(
                    {
                        "event_id": "x",
                        "event_type": "customer.updated",
                        "event_version": 1,
                        "occurred_at": "2026-06-17T12:00:00Z",
                        "source": "odoo",
                        "odoo_company_id": self.env.company.id,
                        "payload": {"odoo_partner_id": 1, "name": "A", "status": "active", "vehicle_limit": 1},
                    }
                ),
            }
        )
        self.env["elmogps.outbox.processor"]._process_single_event(
            event, self.env["elmogps.webhook.client"], self.env.company
        )
        event.invalidate_recordset()
        self.assertIn(event.status, ("failed", "dead"))
        self.assertGreaterEqual(event.attempts, 1)
