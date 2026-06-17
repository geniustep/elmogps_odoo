import uuid
from datetime import datetime, timezone

from odoo import models


class ElmogpsIntegrationEventFactory(models.AbstractModel):
    _name = "elmogps.integration.event.factory"
    _description = "ELMOGPS Integration Event Factory"

    def build_envelope(self, event_type, event_version, company, inner_payload, event_id=None):
        return {
            "event_id": event_id or str(uuid.uuid4()),
            "event_type": event_type,
            "event_version": event_version,
            "occurred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "odoo",
            "odoo_company_id": company.id,
            "payload": inner_payload,
        }
