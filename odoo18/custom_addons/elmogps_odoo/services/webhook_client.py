import logging
import re

import requests

from odoo import models

from .integration_contract import (
    CONNECT_TIMEOUT_SECONDS,
    MAX_BODY_BYTES,
    READ_TIMEOUT_SECONDS,
    WEBHOOK_PATH,
)

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
            return False, 0, "Integration disabled", None
        base_url = company.elmogps_api_base_url
        if not base_url:
            return False, 0, "API base URL not configured", None
        raw_body = event.payload
        if len(raw_body.encode("utf-8")) > MAX_BODY_BYTES:
            return False, 413, "Payload exceeds maximum body size", None
        url = base_url.rstrip("/") + WEBHOOK_PATH
        signer = self.env["elmogps.webhook.signer"]
        headers = signer.build_headers(
            event.event_id,
            event.event_type,
            event.event_version,
            raw_body,
        )
        validation_errors = signer.validate_headers_match_body(headers, raw_body)
        if validation_errors:
            return False, 0, "Header/body mismatch: %s" % ", ".join(validation_errors), None
        timeout = (
            company.elmogps_webhook_timeout
            if company.elmogps_webhook_timeout
            else (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS)
        )
        if isinstance(timeout, int):
            timeout = (CONNECT_TIMEOUT_SECONDS, timeout)
        try:
            response = requests.post(
                url,
                data=raw_body.encode("utf-8"),
                headers=headers,
                timeout=timeout,
            )
            retry_after = response.headers.get("Retry-After")
            return True, response.status_code, response.text[:500], retry_after
        except (requests.RequestException, OSError) as exc:
            error_msg = self._sanitize_error(str(exc))
            return False, 0, error_msg, None
        except Exception as exc:
            error_msg = self._sanitize_error(str(exc))
            return False, 0, error_msg, None

    def _sanitize_error(self, message):
        if SENSITIVE_PATTERN.search(message):
            return "Connection error (details redacted)"
        return message[:500]
