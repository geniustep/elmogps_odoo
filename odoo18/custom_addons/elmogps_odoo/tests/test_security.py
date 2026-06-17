from odoo.tests import tagged

from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestElmogpsSecurity(ElmogpsTestCommon):

    def test_integration_settings_hidden_from_user(self):
        settings = self.env["res.config.settings"].with_user(self.elmogps_user)
        self.assertFalse(
            self.elmogps_user.has_group("elmogps_odoo.group_elmogps_integration_admin")
        )

    def test_sales_can_read_contracts(self):
        contract = self._create_contract()
        contract.with_user(self.elmogps_sales).read(["name", "status"])

    def test_inventory_cannot_create_contract(self):
        with self.assertRaises(Exception):
            self.env["elmogps.contract"].with_user(self.elmogps_inventory).create(
                {
                    "partner_id": self.partner.id,
                    "start_date": "2026-01-01",
                    "end_date": "2026-12-31",
                    "vehicle_limit": 5,
                }
            )
