import os

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    elmogps_integration_enabled = fields.Boolean(
        related="company_id.elmogps_integration_enabled",
        readonly=False,
    )
    elmogps_api_base_url = fields.Char(
        related="company_id.elmogps_api_base_url",
        readonly=False,
    )
    elmogps_webhook_timeout = fields.Integer(
        related="company_id.elmogps_webhook_timeout",
        readonly=False,
    )
    elmogps_webhook_max_attempts = fields.Integer(
        related="company_id.elmogps_webhook_max_attempts",
        readonly=False,
    )
    elmogps_webhook_replay_window = fields.Integer(
        related="company_id.elmogps_webhook_replay_window",
        readonly=False,
    )
    elmogps_integration_environment = fields.Selection(
        related="company_id.elmogps_integration_environment",
        readonly=False,
    )
    elmogps_outbox_batch_size = fields.Integer(
        related="company_id.elmogps_outbox_batch_size",
        readonly=False,
    )
    elmogps_webhook_secret_configured = fields.Boolean(
        compute="_compute_elmogps_webhook_secret_configured",
    )

    @api.depends()
    def _compute_elmogps_webhook_secret_configured(self):
        icp = self.env["ir.config_parameter"].sudo()
        param_secret = icp.get_param("elmogps_odoo.webhook_secret")
        env_secret = os.environ.get("ELMOGPS_ODOO_WEBHOOK_SECRET")
        configured = bool(param_secret or env_secret)
        for record in self:
            record.elmogps_webhook_secret_configured = configured
