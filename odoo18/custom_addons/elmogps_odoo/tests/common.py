import uuid
from datetime import date

from odoo.tests.common import TransactionCase


class ElmogpsTestCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test ELMOGPS Customer",
                "is_elmogps_customer": True,
                "elmogps_vehicle_limit": 10,
            }
        )
        cls.gps_product = cls.env.ref("elmogps_odoo.product_gps_device_template").product_variant_id
        cls.sim_product = cls.env.ref("elmogps_odoo.product_sim_card_template").product_variant_id

        cls.elmogps_user = cls.env["res.users"].create(
            {
                "name": "ELMOGPS User",
                "login": "elmogps_test_user",
                "groups_id": [(6, 0, [cls.env.ref("elmogps_odoo.group_elmogps_user").id])],
            }
        )
        cls.elmogps_sales = cls.env["res.users"].create(
            {
                "name": "ELMOGPS Sales",
                "login": "elmogps_test_sales",
                "groups_id": [(6, 0, [cls.env.ref("elmogps_odoo.group_elmogps_sales").id])],
            }
        )
        cls.elmogps_inventory = cls.env["res.users"].create(
            {
                "name": "ELMOGPS Inventory",
                "login": "elmogps_test_inventory",
                "groups_id": [(6, 0, [cls.env.ref("elmogps_odoo.group_elmogps_inventory").id])],
            }
        )
        cls.technician = cls.env["res.users"].create(
            {
                "name": "ELMOGPS Technician",
                "login": "elmogps_test_technician",
                "groups_id": [(6, 0, [cls.env.ref("elmogps_odoo.group_elmogps_technician").id])],
            }
        )

    def _create_contract(self, active=False):
        contract = self.env["elmogps.contract"].create(
            {
                "partner_id": self.partner.id,
                "start_date": date(2026, 1, 1),
                "end_date": date(2026, 12, 31),
                "vehicle_limit": 5,
            }
        )
        if active:
            contract.action_confirm()
            contract.action_activate()
        return contract

    def _create_vehicle(self, plate="A-12345"):
        return self.env["elmogps.vehicle.reference"].create(
            {
                "name": plate,
                "partner_id": self.partner.id,
                "plate_number": plate,
            }
        )

    def _unique_imei(self):
        suffix = str(uuid.uuid4().int)[-14:]
        return f"1{suffix}"

    def _unique_iccid(self):
        suffix = str(uuid.uuid4().int)[-18:]
        return f"89{suffix}"

    def _create_gps_lot(self, imei=None, name=None):
        imei = imei or self._unique_imei()
        name = name or f"GPS-{uuid.uuid4().hex[:8]}"
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.gps_product.id,
                "company_id": self.env.company.id,
                "elmogps_asset_type": "gps_device",
                "elmogps_imei": imei,
            }
        )

    def _create_sim_lot(self, iccid=None, name=None):
        iccid = iccid or self._unique_iccid()
        name = name or f"SIM-{uuid.uuid4().hex[:8]}"
        return self.env["stock.lot"].create(
            {
                "name": name,
                "product_id": self.sim_product.id,
                "company_id": self.env.company.id,
                "elmogps_asset_type": "sim_card",
                "elmogps_iccid": iccid,
            }
        )

    def _create_installation_ready(self, vehicle=None):
        contract = self._create_contract(active=True)
        vehicle = vehicle or self._create_vehicle()
        gps = self._create_gps_lot()
        sim = self._create_sim_lot()
        return self.env["elmogps.installation"].create(
            {
                "partner_id": self.partner.id,
                "contract_id": contract.id,
                "vehicle_id": vehicle.id,
                "gps_lot_id": gps.id,
                "sim_lot_id": sim.id,
                "technician_id": self.technician.id,
                "scheduled_at": "2026-06-17 10:00:00",
                "installation_type": "new_installation",
                "status": "in_progress",
            }
        )
