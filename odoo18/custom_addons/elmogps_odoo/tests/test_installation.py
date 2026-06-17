from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestElmogpsInstallation(ElmogpsTestCommon):

    def test_cannot_complete_without_requirements(self):
        installation = self.env["elmogps.installation"].create(
            {
                "partner_id": self.partner.id,
                "installation_type": "new_installation",
            }
        )
        with self.assertRaises(UserError):
            installation.action_complete()

    def test_complete_installation(self):
        installation = self._create_installation_ready()
        installation.action_complete()
        self.assertEqual(installation.status, "completed")
        self.assertEqual(installation.gps_lot_id.elmogps_operational_status, "installed")

    def test_remove_installation(self):
        installation = self._create_installation_ready()
        installation.action_complete()
        installation.action_remove()
        self.assertEqual(installation.status, "removed")
        self.assertTrue(installation.removed_at)

    def test_cannot_remove_incomplete(self):
        installation = self.env["elmogps.installation"].create(
            {
                "partner_id": self.partner.id,
                "installation_type": "new_installation",
            }
        )
        with self.assertRaises(UserError):
            installation.action_remove()

    def test_no_double_active_device(self):
        inst1 = self._create_installation_ready()
        gps = inst1.gps_lot_id
        inst1.action_complete()
        inst2 = self._create_installation_ready(
            vehicle=self._create_vehicle(plate="B-99999"),
        )
        inst2.gps_lot_id = gps
        with self.assertRaises(UserError):
            inst2.action_complete()
