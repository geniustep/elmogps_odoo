import uuid

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from odoo.addons.elmogps_odoo.services.integration_contract import (
    SUPPORTED_EVENT_TYPES,
    canonical_json_dumps,
    payload_hash,
    validate_envelope,
)

EVENT_STATUSES = [
    ("pending", "Pending"),
    ("processing", "Processing"),
    ("sent", "Sent"),
    ("failed", "Failed"),
    ("dead", "Dead"),
    ("cancelled", "Cancelled"),
]

class ElmogpsIntegrationEvent(models.Model):
    _name = "elmogps.integration.event"
    _description = "ELMOGPS Integration Outbox Event"
    _inherit = ["mail.thread"]
    _order = "create_date desc, id desc"

    event_id = fields.Char(
        string="Event ID",
        required=True,
        copy=False,
        default=lambda self: str(uuid.uuid4()),
        index=True,
    )
    event_type = fields.Char(string="Event Type", required=True, index=True)
    event_version = fields.Integer(string="Event Version", default=1, required=True)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    model_name = fields.Char(string="Source Model", index=True)
    record_id = fields.Integer(string="Source Record ID", index=True)
    payload = fields.Text(string="Payload JSON", required=True)
    payload_hash = fields.Char(string="Payload Hash", index=True)
    status = fields.Selection(
        selection=EVENT_STATUSES,
        string="Status",
        default="pending",
        required=True,
        tracking=True,
        index=True,
    )
    attempts = fields.Integer(string="Attempts", default=0)
    next_retry_at = fields.Datetime(string="Next Retry At", index=True)
    sent_at = fields.Datetime(string="Sent At")
    last_error = fields.Text(string="Last Error")
    response_status = fields.Integer(string="Response Status")
    created_at = fields.Datetime(
        string="Created At",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    _sql_constraints = [
        (
            "event_id_unique",
            "UNIQUE(event_id)",
            "Event ID must be unique.",
        ),
    ]

    @api.model
    def create_event(self, event_type, record, inner_payload, event_version=1):
        if event_type not in SUPPORTED_EVENT_TYPES:
            raise ValidationError(_("Unsupported event type: %s") % event_type)
        company = getattr(record, "company_id", False) or self.env.company
        event_uuid = str(uuid.uuid4())
        envelope = self.env["elmogps.integration.event.factory"].build_envelope(
            event_type=event_type,
            event_version=event_version,
            company=company,
            inner_payload=inner_payload,
            event_id=event_uuid,
        )
        validation_errors = validate_envelope(envelope)
        if validation_errors:
            raise ValidationError(_("Invalid event envelope: %s") % ", ".join(validation_errors))
        payload_str = canonical_json_dumps(envelope)
        body_hash = payload_hash(payload_str)
        return self.create(
            {
                "event_id": event_uuid,
                "event_type": event_type,
                "event_version": event_version,
                "company_id": company.id,
                "model_name": record._name,
                "record_id": record.id,
                "payload": payload_str,
                "payload_hash": body_hash,
                "status": "pending",
            }
        )

    def action_retry(self):
        for event in self:
            event.write(
                {
                    "status": "pending",
                    "next_retry_at": False,
                    "last_error": False,
                }
            )

    def action_cancel(self):
        for event in self:
            event.status = "cancelled"

    def action_view_payload(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Event Payload"),
            "res_model": "elmogps.integration.event",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
