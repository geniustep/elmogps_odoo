from odoo import fields, models


class ElmogpsIntegrationLog(models.Model):
    _name = "elmogps.integration.log"
    _description = "ELMOGPS Integration Log"
    _order = "create_date desc, id desc"

    event_id = fields.Many2one(
        "elmogps.integration.event",
        string="Event",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        index=True,
    )
    level = fields.Selection(
        selection=[
            ("info", "Info"),
            ("warning", "Warning"),
            ("error", "Error"),
        ],
        string="Level",
        default="info",
        required=True,
    )
    message = fields.Text(string="Message", required=True)
    response_status = fields.Integer(string="Response Status")
    duration_ms = fields.Integer(string="Duration (ms)")
