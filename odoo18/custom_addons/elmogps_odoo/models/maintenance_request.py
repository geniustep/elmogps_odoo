from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    elmogps_installation_id = fields.Many2one(
        "elmogps.installation",
        string="ELMOGPS Installation",
        index=True,
    )
    elmogps_device_lot_id = fields.Many2one(
        "stock.lot",
        string="GPS Device",
        domain="[('elmogps_asset_type', '=', 'gps_device')]",
        index=True,
    )
    elmogps_sim_lot_id = fields.Many2one(
        "stock.lot",
        string="SIM Card",
        domain="[('elmogps_asset_type', '=', 'sim_card')]",
    )
    elmogps_vehicle_id = fields.Many2one(
        "elmogps.vehicle.reference",
        string="Vehicle Reference",
        index=True,
    )
    elmogps_customer_id = fields.Many2one("res.partner", string="ELMOGPS Customer", index=True)
    elmogps_issue_type = fields.Selection(
        selection=[
            ("device_offline", "Device Offline"),
            ("gps_unfixed", "GPS Unfixed"),
            ("gprs_offline", "GPRS Offline"),
            ("power_disconnected", "Power Disconnected"),
            ("sim_issue", "SIM Issue"),
            ("installation_issue", "Installation Issue"),
            ("hardware_failure", "Hardware Failure"),
            ("replacement", "Replacement"),
            ("other", "Other"),
        ],
        string="Issue Type",
        default="other",
    )
    elmogps_resolution = fields.Text(string="Resolution")
    elmogps_warranty_case = fields.Boolean(string="Warranty Case")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        builder = self.env["elmogps.integration.payload.builder"]
        for record in records.filtered(lambda r: r.elmogps_customer_id or r.elmogps_device_lot_id):
            self.env["elmogps.integration.event"].sudo().create_event(
                "maintenance.opened",
                record,
                builder.build_maintenance_opened_payload(record),
            )
        return records

    def write(self, vals):
        previously_closed = {}
        if vals.get("stage_id") or vals.get("archive"):
            for record in self:
                previously_closed[record.id] = bool(
                    record.archive or (record.stage_id and record.stage_id.done)
                )
        res = super().write(vals)
        builder = self.env["elmogps.integration.payload.builder"]
        if vals.get("stage_id") or vals.get("archive"):
            for record in self:
                now_closed = bool(
                    record.archive or (record.stage_id and record.stage_id.done)
                )
                if now_closed and not previously_closed.get(record.id):
                    self.env["elmogps.integration.event"].sudo().create_event(
                        "maintenance.closed",
                        record,
                        builder.build_maintenance_closed_payload(record),
                    )
        return res

    def action_send_to_maintenance_stock(self):
        for record in self:
            if not record.elmogps_device_lot_id:
                raise UserError(_("A GPS device lot is required."))
            record.elmogps_device_lot_id.elmogps_operational_status = "maintenance"
