from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    elmogps_integration_enabled = fields.Boolean(
        string="ELMOGPS Integration Enabled",
        default=False,
    )
    elmogps_api_base_url = fields.Char(string="ELMOGPS API Base URL")
    elmogps_webhook_timeout = fields.Integer(string="Webhook Timeout (seconds)", default=30)
    elmogps_webhook_max_attempts = fields.Integer(string="Webhook Max Attempts", default=8)
    elmogps_webhook_replay_window = fields.Integer(
        string="Webhook Replay Window (seconds)", default=300
    )
    elmogps_integration_environment = fields.Selection(
        selection=[
            ("disabled", "Disabled"),
            ("development", "Development"),
            ("staging", "Staging"),
            ("production", "Production"),
        ],
        string="Integration Environment",
        default="disabled",
    )
    elmogps_outbox_batch_size = fields.Integer(string="Outbox Batch Size", default=50)
