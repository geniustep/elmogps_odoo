import hashlib
import hmac

from odoo import models


class ElmogpsWebhookSigner(models.AbstractModel):
    _name = "elmogps.webhook.signer"
    _description = "ELMOGPS Webhook HMAC Signer"

    def get_secret(self):
        icp = self.env["ir.config_parameter"].sudo()
        import os

        return os.environ.get("ELMOGPS_ODOO_WEBHOOK_SECRET") or icp.get_param(
            "elmogps_odoo.webhook_secret"
        )

    def sign(self, timestamp, raw_body, secret=None):
        secret = secret or self.get_secret()
        if not secret:
            return None
        message = f"{timestamp}.{raw_body}".encode("utf-8")
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def build_headers(self, event_id, event_version, raw_body, timestamp=None):
        import time

        timestamp = timestamp or str(int(time.time()))
        signature = self.sign(timestamp, raw_body)
        headers = {
            "Content-Type": "application/json",
            "X-ELMOGPS-Event-Id": event_id,
            "X-ELMOGPS-Timestamp": timestamp,
            "X-ELMOGPS-Event-Version": str(event_version),
        }
        if signature:
            headers["X-ELMOGPS-Signature"] = signature
        return headers
