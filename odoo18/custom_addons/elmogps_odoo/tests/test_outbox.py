import json
from unittest.mock import patch

import uuid

from psycopg2 import IntegrityError

from odoo.tests import tagged

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
        with patch.dict("os.environ", {"ELMOGPS_ODOO_WEBHOOK_SECRET": "test-secret"}):
            sig = signer.sign("1234567890", '{"a":1}', secret="test-secret")
        self.assertEqual(
            sig,
            signer.sign("1234567890", '{"a":1}', secret="test-secret"),
        )

    def test_disabled_integration_skips_send(self):
        self.env.company.elmogps_integration_enabled = False
        event = self.env["elmogps.integration.event"].create(
            {
                "event_type": "customer.updated",
                "payload": '{"event_type":"customer.updated"}',
            }
        )
        success, status, msg = self.env["elmogps.webhook.client"].send_event(event)
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
                "payload": '{"event_type":"customer.updated","event_id":"x"}',
            }
        )
        self.env["elmogps.outbox.processor"]._process_single_event(
            event, self.env["elmogps.webhook.client"], self.env.company
        )
        event.invalidate_recordset()
        self.assertIn(event.status, ("failed", "dead"))
        self.assertGreaterEqual(event.attempts, 1)
