from datetime import timedelta

from odoo import api, fields, models


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

        success, status_code, message = client.send_event(event)
        max_attempts = company.elmogps_webhook_max_attempts or 5
        attempts = event.attempts + 1

        if success and 200 <= status_code < 300:
            event.write(
                {
                    "status": "sent",
                    "attempts": attempts,
                    "sent_at": fields.Datetime.now(),
                    "response_status": status_code,
                    "last_error": False,
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
        else:
            if attempts >= max_attempts:
                new_status = "dead"
            else:
                new_status = "failed"
            retry_delay = min(300, 30 * (2 ** (attempts - 1)))
            event.write(
                {
                    "status": new_status,
                    "attempts": attempts,
                    "next_retry_at": fields.Datetime.now() + timedelta(seconds=retry_delay),
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
