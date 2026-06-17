from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    elmogps_contract_id = fields.Many2one("elmogps.contract", string="ELMOGPS Contract")

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if order.elmogps_contract_id and order.elmogps_contract_id.status == "confirmed":
                order.elmogps_contract_id.action_activate()
        return res
