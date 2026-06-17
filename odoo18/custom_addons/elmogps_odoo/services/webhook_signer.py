import os
import time

from odoo import models

from .integration_contract import (
    build_signature_headers,
    sign_body,
    validate_headers_match_body,
)


class ElmogpsWebhookSigner(models.AbstractModel):
    _name = "elmogps.webhook.signer"
    _description = "ELMOGPS Webhook HMAC Signer"

    def get_secret(self):
        icp = self.env["ir.config_parameter"].sudo()
        return os.environ.get("ELMOGPS_ODOO_WEBHOOK_SECRET") or icp.get_param(
            "elmogps_odoo.webhook_secret"
        )

    def sign(self, timestamp, raw_body, secret=None):
        secret = secret or self.get_secret()
        if not secret:
            return None
        return sign_body(timestamp, raw_body, secret)

    def build_headers(self, event_id, event_type, event_version, raw_body, timestamp=None):
        timestamp = timestamp or str(int(time.time()))
        secret = self.get_secret()
        if not secret:
            return {
                "Content-Type": "application/json",
                "User-Agent": "elmogps-odoo/18.0",
                "X-ELMOGPS-Event-Id": event_id,
                "X-ELMOGPS-Event-Type": event_type,
                "X-ELMOGPS-Event-Version": str(event_version),
                "X-ELMOGPS-Timestamp": timestamp,
            }
        return build_signature_headers(
            event_id, event_type, event_version, raw_body, timestamp, secret
        )

    def validate_headers_match_body(self, headers, raw_body):
        import json

        envelope = json.loads(raw_body)
        return validate_headers_match_body(headers, envelope)
