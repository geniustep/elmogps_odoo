import uuid

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestElmogpsDeviceSim(ElmogpsTestCommon):

    def test_imei_unique(self):
        imei = self._unique_imei()
        self._create_gps_lot(imei=imei)
        with self.assertRaises(Exception):
            self._create_gps_lot(imei=imei, name="GPS-002")

    def test_imei_normalization(self):
        lot = self._create_gps_lot(imei="12345 678-9012345")
        self.assertEqual(lot.elmogps_imei, "123456789012345")

    def test_invalid_imei(self):
        with self.assertRaises(ValidationError):
            self._create_gps_lot(imei="123")

    def test_iccid_unique(self):
        iccid = self._unique_iccid()
        self._create_sim_lot(iccid=iccid)
        with self.assertRaises(Exception):
            self._create_sim_lot(iccid=iccid, name="SIM-002")

    def test_gps_requires_serial_tracking(self):
        with self.assertRaises(ValidationError):
            self.env["product.template"].create(
                {
                    "name": "Bad GPS",
                    "type": "consu",
                    "is_storable": True,
                    "tracking": "none",
                    "elmogps_product_type": "gps_device",
                }
            )
