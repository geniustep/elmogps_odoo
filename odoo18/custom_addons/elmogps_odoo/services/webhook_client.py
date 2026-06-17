import logging
import re

import requests

from odoo import models

_logger = logging.getLogger(__name__)

SENSITIVE_PATTERN = re.compile(
    r"(password|secret|token|authorization)", re.IGNORECASE
)


class ElmogpsWebhookClient(models.AbstractModel):
    _name = "elmogps.webhook.client"
    _description = "ELMOGPS Webhook HTTP Client"

    def send_event(self, event):
        company = event.company_id
        if not company.elmogps_integration_enabled:
            return False, 0, "Integration disabled"
        base_url = company.elmogps_api_base_url
        if not base_url:
            return False, 0, "API base URL not configured"
        url = base_url.rstrip("/") + "/webhooks/odoo"
        timeout = company.elmogps_webhook_timeout or 30
        signer = self.env["elmogps.webhook.signer"]
        headers = signer.build_headers(event.event_id, event.event_version, event.payload)
        try:
            response = requests.post(
                url,
                data=event.payload,
                headers=headers,
                timeout=timeout,
            )
            return True, response.status_code, response.text[:500]
        except (requests.RequestException, OSError) as exc:
            error_msg = self._sanitize_error(str(exc))
            return False, 0, error_msg
        except Exception as exc:
            error_msg = self._sanitize_error(str(exc))
            return False, 0, error_msg

    def _sanitize_error(self, message):
        if SENSITIVE_PATTERN.search(message):
            return "Connection error (details redacted)"
        return message[:500]
