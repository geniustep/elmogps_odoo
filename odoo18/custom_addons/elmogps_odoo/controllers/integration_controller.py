import json

from odoo import http
from odoo.http import request


class ElmogpsIntegrationController(http.Controller):

    @http.route("/elmogps/integration/health", type="json", auth="user", methods=["POST"])
    def health(self):
        user = request.env.user
        if not user.has_group("elmogps_odoo.group_elmogps_integration_admin"):
            return {"status": "forbidden"}
        company = request.env.company
        secret_configured = bool(
            request.env["elmogps.webhook.signer"].get_secret()
        )
        pending = request.env["elmogps.integration.event"].search_count(
            [("company_id", "=", company.id), ("status", "in", ("pending", "failed"))]
        )
        return {
            "status": "ok",
            "integration_enabled": company.elmogps_integration_enabled,
            "environment": company.elmogps_integration_environment,
            "secret_configured": secret_configured,
            "pending_events": pending,
        }
