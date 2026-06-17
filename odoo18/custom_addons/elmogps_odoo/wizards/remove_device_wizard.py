from odoo import fields, models


class ElmogpsRemoveDeviceWizard(models.TransientModel):
    _name = "elmogps.remove.device.wizard"
    _description = "Remove Device Wizard"

    installation_id = fields.Many2one(
        "elmogps.installation",
        string="Installation",
        required=True,
    )
    return_to_stock = fields.Boolean(string="Return Device to Stock", default=True)
    notes = fields.Text(string="Removal Notes")

    def action_confirm_remove(self):
        self.ensure_one()
        if self.notes:
            self.installation_id.message_post(body=self.notes)
        self.installation_id.action_remove()
        if self.return_to_stock and self.installation_id.gps_lot_id:
            self.installation_id.gps_lot_id.action_return_to_stock()
        return {"type": "ir.actions.act_window_close"}
