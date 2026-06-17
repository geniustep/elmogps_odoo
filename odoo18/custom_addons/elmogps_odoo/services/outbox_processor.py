from datetime import timedelta

from odoo import api, fields, models

from .integration_contract import (
    MAX_ATTEMPTS_DEFAULT,
    classify_delivery_result,
    next_retry_delay_seconds,
)


class ElmogpsOutboxProcessor(models.AbstractModel):
    _name = "elmogps.outbox.processor"
    _description = "ELMOGPS Outbox Processor"

    @api.model
    def process_pending_events(self):
        companies = self.env["res.company"].search([("elmogps_integration_enabled", "=", True)])
        if not companies:
            return
        Event = self.env["elmogps.integration.event"]
        client = self.env["elmogps.webhook.client"]
        now = fields.Datetime.now()
        for company in companies:
            batch_size = company.elmogps_outbox_batch_size or 50
            domain = [
                ("company_id", "=", company.id),
                ("status", "in", ("pending", "failed")),
                "|",
                ("next_retry_at", "=", False),
                ("next_retry_at", "<=", now),
            ]
            events = Event.search(domain, limit=batch_size, order="create_date asc")
            for event in events:
                self._process_single_event(event, client, company)

    def _process_single_event(self, event, client, company):
        Event = self.env["elmogps.integration.event"]
        locked = Event.search(
            [("id", "=", event.id), ("status", "in", ("pending", "failed"))]
        )
        if not locked:
            return
        event.write({"status": "processing"})

        success, status_code, message, retry_after = client.send_event(event)
        max_attempts = company.elmogps_webhook_max_attempts or MAX_ATTEMPTS_DEFAULT
        attempts = event.attempts + 1
        delivered, retryable = classify_delivery_result(success, status_code)

        if delivered:
            event.write(
                {
                    "status": "sent",
                    "attempts": attempts,
                    "sent_at": fields.Datetime.now(),
                    "response_status": status_code,
                    "last_error": False,
                    "next_retry_at": False,
                }
            )
            self.env["elmogps.integration.log"].create(
                {
                    "event_id": event.id,
                    "company_id": company.id,
                    "level": "info",
                    "message": "Event sent successfully",
                    "response_status": status_code,
                }
            )
            return

        if not retryable:
            new_status = "dead"
            next_retry = False
        elif attempts >= max_attempts:
            new_status = "dead"
            next_retry = False
        else:
            new_status = "failed"
            delay = next_retry_delay_seconds(attempts)
            if retry_after and str(retry_after).isdigit():
                delay = max(delay, int(retry_after))
            next_retry = fields.Datetime.now() + timedelta(seconds=delay)

        event.write(
            {
                "status": new_status,
                "attempts": attempts,
                "next_retry_at": next_retry,
                "response_status": status_code or 0,
                "last_error": message,
            }
        )
        self.env["elmogps.integration.log"].create(
            {
                "event_id": event.id,
                "company_id": company.id,
                "level": "error",
                "message": message or "Delivery failed",
                "response_status": status_code or 0,
            }
        )
