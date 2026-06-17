from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestElmogpsContract(ElmogpsTestCommon):

    def test_contract_activation_requires_fields(self):
        contract = self.env["elmogps.contract"].create(
            {
                "partner_id": self.partner.id,
                "vehicle_limit": 5,
            }
        )
        with self.assertRaises(Exception):
            contract.action_activate()

    def test_contract_lifecycle(self):
        contract = self._create_contract()
        contract.action_confirm()
        self.assertEqual(contract.status, "confirmed")
        contract.action_activate()
        self.assertEqual(contract.status, "active")
        contract.action_suspend()
        self.assertEqual(contract.status, "suspended")

    def test_end_date_before_start(self):
        with self.assertRaises(ValidationError):
            self.env["elmogps.contract"].create(
                {
                    "partner_id": self.partner.id,
                    "start_date": "2026-12-31",
                    "end_date": "2026-01-01",
                    "vehicle_limit": 1,
                }
            )

    def test_vehicle_limit(self):
        contract = self._create_contract(active=True)
        self.assertTrue(contract.check_vehicle_limit(extra=0))
        self.assertFalse(contract.check_vehicle_limit(extra=100))
