from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ElmogpsAllocateDeviceWizard(models.TransientModel):
    _name = "elmogps.allocate.device.wizard"
    _description = "Allocate ELMOGPS Device Wizard"

    lot_id = fields.Many2one("stock.lot", string="Device/SIM", required=True)
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    contract_id = fields.Many2one(
        "elmogps.contract",
        string="Contract",
        domain="[('partner_id', '=', partner_id), ('status', '=', 'active')]",
    )

    def action_allocate(self):
        self.ensure_one()
        if not self.partner_id.is_elmogps_customer:
            raise UserError(_("Partner must be an ELMOGPS customer."))
        event_type = (
            "device.allocated"
            if self.lot_id.elmogps_asset_type == "gps_device"
            else "sim.allocated"
        )
        self.lot_id.write(
            {
                "elmogps_operational_status": "allocated",
                "elmogps_customer_id": self.partner_id.id,
            }
        )
        self.env["elmogps.integration.event"].sudo().create_event(
            event_type,
            self.lot_id,
            self.env["elmogps.integration.payload.builder"].build_lot_payload(self.lot_id),
        )
        return {"type": "ir.actions.act_window_close"}
