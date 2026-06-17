import json
import os
from unittest.mock import MagicMock, patch

from odoo.tests import tagged

from odoo.addons.elmogps_odoo.services.integration_contract import (
    TEST_SECRET,
    canonical_json_dumps,
    classify_delivery_result,
    contains_forbidden_secrets,
    next_retry_delay_seconds,
    payload_hash,
    sign_body,
    validate_envelope,
)
from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestIntegrationContract(ElmogpsTestCommon):

    def _sample_envelope(self, event_type="installation.completed"):
        return {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": event_type,
            "event_version": 1,
            "occurred_at": "2026-06-17T12:00:00Z",
            "source": "odoo",
            "odoo_company_id": self.env.company.id,
            "payload": {"odoo_installation_id": 1},
        }

    def test_envelope_validation_ok(self):
        self.assertEqual(validate_envelope(self._sample_envelope()), [])

    def test_envelope_rejects_missing_field(self):
        envelope = self._sample_envelope()
        del envelope["event_id"]
        self.assertIn("missing:event_id", validate_envelope(envelope))

    def test_envelope_rejects_unknown_event_type(self):
        envelope = self._sample_envelope("not.valid")
        self.assertIn("invalid:event_type", validate_envelope(envelope))

    def test_envelope_rejects_secrets_in_payload(self):
        envelope = self._sample_envelope()
        envelope["payload"]["webhook_secret"] = "hidden"
        self.assertIn("forbidden:secrets_in_payload", validate_envelope(envelope))

    def test_canonical_json_stable(self):
        data = {"b": 2, "a": 1, "nested": {"z": 1, "y": 2}}
        first = canonical_json_dumps(data)
        second = canonical_json_dumps(data)
        self.assertEqual(first, second)
        self.assertEqual(payload_hash(first), payload_hash(second))

    def test_hmac_test_vector(self):
        module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        vector_path = os.path.join(
            module_root,
            "docs/integration-contract/v1/test-vectors/hmac-sha256.json",
        )
        with open(vector_path, encoding="utf-8") as handle:
            vector = json.load(handle)
        signature = sign_body(vector["timestamp"], vector["raw_body"], vector["test_secret"])
        self.assertEqual(signature, vector["expected_signature"])
        self.assertTrue(signature.startswith("sha256="))

    def test_hmac_changes_with_body_or_timestamp(self):
        body = canonical_json_dumps(self._sample_envelope())
        sig1 = sign_body("1000", body, TEST_SECRET)
        sig2 = sign_body("1001", body, TEST_SECRET)
        sig3 = sign_body("1000", body + " ", TEST_SECRET)
        self.assertNotEqual(sig1, sig2)
        self.assertNotEqual(sig1, sig3)

    def test_signer_headers_match_body(self):
        envelope = self._sample_envelope()
        raw_body = canonical_json_dumps(envelope)
        signer = self.env["elmogps.webhook.signer"]
        with patch.dict("os.environ", {"ELMOGPS_ODOO_WEBHOOK_SECRET": TEST_SECRET}):
            headers = signer.build_headers(
                envelope["event_id"],
                envelope["event_type"],
                envelope["event_version"],
                raw_body,
                timestamp="1718625600",
            )
            self.assertEqual(headers["X-ELMOGPS-Event-Type"], "installation.completed")
            self.assertTrue(headers["X-ELMOGPS-Signature"].startswith("sha256="))
            self.assertEqual(signer.validate_headers_match_body(headers, raw_body), [])

    def test_imei_and_iccid_remain_strings_in_payload(self):
        gps = self._create_gps_lot(imei="100000000000001")
        sim = self._create_sim_lot(iccid="89014103211118510888")
        builder = self.env["elmogps.integration.payload.builder"]
        device_payload = builder.build_device_allocated_payload(gps)
        sim_payload = builder.build_sim_allocated_payload(sim)
        self.assertIsInstance(device_payload["imei"], str)
        self.assertIsInstance(sim_payload["iccid"], str)

    def test_retry_classification(self):
        self.assertEqual(classify_delivery_result(True, 202), (True, False))
        self.assertEqual(classify_delivery_result(True, 200), (True, False))
        self.assertEqual(classify_delivery_result(True, 400), (False, False))
        self.assertEqual(classify_delivery_result(True, 401), (False, False))
        self.assertEqual(classify_delivery_result(True, 409), (False, False))
        self.assertEqual(classify_delivery_result(True, 422), (False, False))
        self.assertEqual(classify_delivery_result(True, 429), (False, True))
        self.assertEqual(classify_delivery_result(True, 503), (False, True))
        self.assertEqual(classify_delivery_result(False, 0), (False, True))

    def test_retry_schedule_matches_contract(self):
        self.assertEqual(next_retry_delay_seconds(1), 60)
        self.assertEqual(next_retry_delay_seconds(2), 300)
        self.assertEqual(next_retry_delay_seconds(8), 172800)

    def _create_contract_event(self, event_type="customer.updated"):
        envelope = self._sample_envelope(event_type)
        raw_body = canonical_json_dumps(envelope)
        return self.env["elmogps.integration.event"].create(
            {
                "event_id": envelope["event_id"],
                "event_type": event_type,
                "event_version": 1,
                "payload": raw_body,
                "payload_hash": payload_hash(raw_body),
            }
        )

    def test_event_id_stable_on_manual_retry(self):
        event = self.env["elmogps.integration.event"].create(
            {
                "event_type": "customer.updated",
                "payload": canonical_json_dumps(self._sample_envelope("customer.updated")),
            }
        )
        original_id = event.event_id
        original_payload = event.payload
        event.action_retry()
        self.assertEqual(event.event_id, original_id)
        self.assertEqual(event.payload, original_payload)

    def test_disabled_integration_skips_http(self):
        self.env.company.elmogps_integration_enabled = False
        event = self.env["elmogps.integration.event"].create(
            {
                "event_type": "customer.updated",
                "payload": canonical_json_dumps(self._sample_envelope("customer.updated")),
            }
        )
        with patch("odoo.addons.elmogps_odoo.services.webhook_client.requests.post") as mock_post:
            success, status, _msg, _retry = self.env["elmogps.webhook.client"].send_event(event)
        self.assertFalse(success)
        mock_post.assert_not_called()

    @patch("odoo.addons.elmogps_odoo.services.webhook_client.requests.post")
    def test_success_202_marks_sent(self, mock_post):
        response = MagicMock()
        response.status_code = 202
        response.text = '{"status":"accepted"}'
        response.headers = {}
        mock_post.return_value = response
        self.env.company.write(
            {
                "elmogps_integration_enabled": True,
                "elmogps_api_base_url": "https://example.test",
            }
        )
        with patch.dict("os.environ", {"ELMOGPS_ODOO_WEBHOOK_SECRET": TEST_SECRET}):
            event = self._create_contract_event()
            self.env["elmogps.outbox.processor"]._process_single_event(
                event, self.env["elmogps.webhook.client"], self.env.company
            )
        event.invalidate_recordset()
        self.assertEqual(event.status, "sent")
        called_url = mock_post.call_args[0][0]
        self.assertTrue(called_url.endswith("/api/v1/integrations/odoo/events"))

    @patch("odoo.addons.elmogps_odoo.services.webhook_client.requests.post")
    def test_non_retryable_400_goes_dead(self, mock_post):
        response = MagicMock()
        response.status_code = 400
        response.text = '{"error":{"code":"bad_request"}}'
        response.headers = {}
        mock_post.return_value = response
        self.env.company.write(
            {
                "elmogps_integration_enabled": True,
                "elmogps_api_base_url": "https://example.test",
                "elmogps_webhook_max_attempts": 8,
            }
        )
        with patch.dict("os.environ", {"ELMOGPS_ODOO_WEBHOOK_SECRET": TEST_SECRET}):
            event = self._create_contract_event()
            self.env["elmogps.outbox.processor"]._process_single_event(
                event, self.env["elmogps.webhook.client"], self.env.company
            )
        event.invalidate_recordset()
        self.assertEqual(event.status, "dead")

    def test_customer_activation_single_event(self):
        partner = self.env["res.partner"].create(
            {"name": "Contract Activation Partner", "is_elmogps_customer": True}
        )
        before = self.env["elmogps.integration.event"].search_count(
            [("record_id", "=", partner.id), ("model_name", "=", "res.partner")]
        )
        partner.action_activate_elmogps_customer()
        events = self.env["elmogps.integration.event"].search(
            [("record_id", "=", partner.id), ("model_name", "=", "res.partner")]
        )
        self.assertEqual(len(events), before + 1)
        self.assertEqual(events[-1].event_type, "customer.activated")

    def test_contains_forbidden_secrets_helper(self):
        self.assertFalse(contains_forbidden_secrets({"imei": "123"}))
        self.assertTrue(contains_forbidden_secrets({"api_secret": "x"}))
