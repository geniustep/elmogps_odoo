import json
import os
import uuid

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.elmogps_odoo.services.integration_contract import (
    canonical_json_dumps,
    optional_external_uuid,
    sign_body,
    TEST_SECRET,
)
from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None

VALID_DEVICE_UUID = "550e8400-e29b-41d4-a716-446655440000"


@tagged("post_install", "-at_install")
class TestMaintenanceDeviceReference(ElmogpsTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.module_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        cls.schema_dir = os.path.join(
            cls.module_root, "docs/integration-contract/v1/events"
        )

    def _load_schema(self, filename):
        path = os.path.join(self.schema_dir, filename)
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def _validate_payload(self, schema_name, payload):
        if Draft202012Validator is not None:
            schema = self._load_schema(schema_name)
            Draft202012Validator(schema).validate(payload)
            return
        if schema_name == "maintenance.opened.schema.json":
            self.assertIsInstance(payload["odoo_maintenance_id"], int)
            self.assertIn(payload.get("elmogps_device_id"), (None, VALID_DEVICE_UUID))
            self.assertFalse(payload["elmogps_device_id"] is False)
            self.assertIn(payload.get("elmogps_tenant_id"), (None, VALID_DEVICE_UUID))
            return
        if schema_name == "maintenance.closed.schema.json":
            self.assertIsInstance(payload["odoo_maintenance_id"], int)
            self.assertEqual(payload["status"], "closed")
            self.assertIn(payload.get("elmogps_device_id"), (None, VALID_DEVICE_UUID))
            self.assertFalse(payload["elmogps_device_id"] is False)
            return
        self.skipTest("jsonschema not installed for %s" % schema_name)

    def _create_maintenance(self, gps_lot=None):
        contract = self._create_contract(active=True)
        vehicle = self._create_vehicle(plate=f"MNT-{uuid.uuid4().hex[:6]}")
        gps = gps_lot or self._create_gps_lot()
        return self.env["maintenance.request"].create(
            {
                "name": f"Maintenance {uuid.uuid4().hex[:8]}",
                "elmogps_customer_id": self.partner.id,
                "elmogps_device_lot_id": gps.id,
                "elmogps_vehicle_id": vehicle.id,
                "elmogps_issue_type": "device_offline",
            }
        )

    def test_optional_external_uuid_helper(self):
        self.assertIsNone(optional_external_uuid(None))
        self.assertIsNone(optional_external_uuid(False))
        self.assertIsNone(optional_external_uuid(""))
        self.assertIsNone(optional_external_uuid("   "))
        self.assertEqual(
            optional_external_uuid(VALID_DEVICE_UUID),
            VALID_DEVICE_UUID,
        )
        with self.assertRaises(Exception):
            optional_external_uuid("not-a-uuid", strict=True)

    def test_maintenance_opened_without_device_uuid_emits_null(self):
        maintenance = self._create_maintenance()
        self.assertFalse(maintenance.elmogps_device_lot_id.elmogps_device_id)
        builder = self.env["elmogps.integration.payload.builder"]
        payload = builder.build_maintenance_opened_payload(maintenance)
        self.assertIsNone(payload["elmogps_device_id"])
        self.assertIsNone(payload["elmogps_tenant_id"])
        self.assertEqual(payload["odoo_stock_lot_id"], maintenance.elmogps_device_lot_id.id)
        self.assertIsInstance(payload["warranty_case"], bool)
        serialized = canonical_json_dumps(payload)
        self.assertIn('"elmogps_device_id":null', serialized)
        self.assertNotIn('"elmogps_device_id":false', serialized)
        self._validate_payload("maintenance.opened.schema.json", payload)

    def test_maintenance_opened_with_real_device_uuid(self):
        gps = self._create_gps_lot()
        gps.write({"elmogps_device_id": VALID_DEVICE_UUID})
        maintenance = self._create_maintenance(gps_lot=gps)
        payload = self.env["elmogps.integration.payload.builder"].build_maintenance_opened_payload(
            maintenance
        )
        self.assertEqual(payload["elmogps_device_id"], VALID_DEVICE_UUID)
        self._validate_payload("maintenance.opened.schema.json", payload)

    def test_maintenance_closed_without_device_uuid_emits_null(self):
        maintenance = self._create_maintenance()
        payload = self.env["elmogps.integration.payload.builder"].build_maintenance_closed_payload(
            maintenance
        )
        self.assertIsNone(payload["elmogps_device_id"])
        serialized = canonical_json_dumps(payload)
        self.assertIn('"elmogps_device_id":null', serialized)
        self._validate_payload("maintenance.closed.schema.json", payload)

    def test_maintenance_closed_with_real_device_uuid(self):
        gps = self._create_gps_lot()
        gps.write({"elmogps_device_id": VALID_DEVICE_UUID})
        maintenance = self._create_maintenance(gps_lot=gps)
        payload = self.env["elmogps.integration.payload.builder"].build_maintenance_closed_payload(
            maintenance
        )
        self.assertEqual(payload["elmogps_device_id"], VALID_DEVICE_UUID)
        self._validate_payload("maintenance.closed.schema.json", payload)

    def test_invalid_device_uuid_rejected(self):
        builder = self.env["elmogps.integration.payload.builder"]
        with self.assertRaises(ValidationError):
            builder._external_uuid("not-a-valid-uuid")

    def test_schema_rejects_false_for_device_uuid(self):
        payload = {
            "odoo_maintenance_id": 1,
            "odoo_partner_id": 1,
            "odoo_installation_id": None,
            "odoo_stock_lot_id": 99,
            "elmogps_tenant_id": None,
            "elmogps_device_id": False,
            "issue_type": "device_offline",
            "opened_at": "2026-06-17T12:00:00Z",
            "warranty_case": False,
        }
        if Draft202012Validator is not None:
            schema = self._load_schema("maintenance.opened.schema.json")
            with self.assertRaises(Exception):
                Draft202012Validator(schema).validate(payload)
        else:
            self.assertTrue(payload["elmogps_device_id"] is False)
            fixed = dict(payload)
            fixed["elmogps_device_id"] = None
            self._validate_payload("maintenance.opened.schema.json", fixed)

    def test_installation_device_block_serializes_null_not_false(self):
        gps = self._create_gps_lot()
        inst = self._create_installation_ready()
        inst.gps_lot_id = gps
        payload = self.env["elmogps.integration.payload.builder"].build_installation_completed_payload(
            inst
        )
        self.assertIsNone(payload["device"]["elmogps_device_id"])
        serialized = canonical_json_dumps(payload)
        self.assertIn('"elmogps_device_id":null', serialized)

    def test_no_random_uuid_generated_in_maintenance_payload(self):
        maintenance = self._create_maintenance()
        payload = self.env["elmogps.integration.payload.builder"].build_maintenance_opened_payload(
            maintenance
        )
        self.assertIsNone(payload["elmogps_device_id"])

    def test_maintenance_closed_emitted_once_on_repeated_writes(self):
        maintenance = self._create_maintenance()
        done_stage = self.env["maintenance.stage"].search([("done", "=", True)], limit=1)
        maintenance.write({"stage_id": done_stage.id})
        first_count = self.env["elmogps.integration.event"].search_count(
            [
                ("model_name", "=", "maintenance.request"),
                ("record_id", "=", maintenance.id),
                ("event_type", "=", "maintenance.closed"),
            ]
        )
        maintenance.write({"elmogps_resolution": "Checked again"})
        second_count = self.env["elmogps.integration.event"].search_count(
            [
                ("model_name", "=", "maintenance.request"),
                ("record_id", "=", maintenance.id),
                ("event_type", "=", "maintenance.closed"),
            ]
        )
        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)

    def test_hmac_vector_unchanged(self):
        module_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        vector_path = os.path.join(
            module_root,
            "docs/integration-contract/v1/test-vectors/hmac-sha256.json",
        )
        with open(vector_path, encoding="utf-8") as handle:
            vector = json.load(handle)
        signature = sign_body(vector["timestamp"], vector["raw_body"], vector["test_secret"])
        self.assertEqual(signature, vector["expected_signature"])

    def test_all_event_schemas_still_load(self):
        schema_files = sorted(
            name
            for name in os.listdir(self.schema_dir)
            if name.endswith(".schema.json")
        )
        self.assertEqual(len(schema_files), 16)
        for name in schema_files:
            with open(os.path.join(self.schema_dir, name), encoding="utf-8") as handle:
                json.load(handle)

    def test_canonical_serialization_stable_for_null_uuid(self):
        payload = {
            "odoo_maintenance_id": 1,
            "elmogps_device_id": None,
            "issue_type": "other",
            "opened_at": "2026-06-17T12:00:00Z",
            "warranty_case": False,
        }
        first = canonical_json_dumps(payload)
        second = canonical_json_dumps(payload)
        self.assertEqual(first, second)
        self.assertIn("null", first)
