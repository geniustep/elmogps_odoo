import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

ELMOGPS_SERVICE_STATUSES = [
    ("draft", "Draft"),
    ("trial", "Trial"),
    ("active", "Active"),
    ("suspended", "Suspended"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
]

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_elmogps_customer = fields.Boolean(string="ELMOGPS Customer", index=True)
    elmogps_customer_code = fields.Char(string="ELMOGPS Customer Code", copy=False)
    elmogps_tenant_id = fields.Char(string="ELMOGPS Tenant ID", copy=False, index=True)
    elmogps_service_status = fields.Selection(
        selection=ELMOGPS_SERVICE_STATUSES,
        string="ELMOGPS Service Status",
        default="draft",
        tracking=True,
        index=True,
    )
    elmogps_activation_date = fields.Date(string="Activation Date")
    elmogps_suspension_date = fields.Date(string="Suspension Date")
    elmogps_vehicle_limit = fields.Integer(string="Vehicle Limit", default=0)
    elmogps_notes = fields.Text(string="ELMOGPS Notes")

    elmogps_contract_count = fields.Integer(compute="_compute_elmogps_counts")
    elmogps_installation_count = fields.Integer(compute="_compute_elmogps_counts")
    elmogps_device_count = fields.Integer(compute="_compute_elmogps_counts")
    elmogps_vehicle_count = fields.Integer(compute="_compute_elmogps_counts")

    @api.depends("is_elmogps_customer")
    def _compute_elmogps_counts(self):
        Contract = self.env["elmogps.contract"]
        Installation = self.env["elmogps.installation"]
        Vehicle = self.env["elmogps.vehicle.reference"]
        Lot = self.env["stock.lot"]
        for partner in self:
            if not partner.is_elmogps_customer:
                partner.elmogps_contract_count = 0
                partner.elmogps_installation_count = 0
                partner.elmogps_device_count = 0
                partner.elmogps_vehicle_count = 0
                continue
            partner.elmogps_contract_count = Contract.search_count(
                [("partner_id", "=", partner.id)]
            )
            partner.elmogps_installation_count = Installation.search_count(
                [("partner_id", "=", partner.id)]
            )
            partner.elmogps_vehicle_count = Vehicle.search_count(
                [("partner_id", "=", partner.id)]
            )
            partner.elmogps_device_count = Lot.search_count(
                [
                    ("elmogps_asset_type", "=", "gps_device"),
                    ("elmogps_customer_id", "=", partner.id),
                ]
            )

    @api.constrains("elmogps_tenant_id")
    def _check_elmogps_tenant_id(self):
        for partner in self:
            if partner.elmogps_tenant_id and not UUID_PATTERN.match(partner.elmogps_tenant_id):
                raise ValidationError(_("ELMOGPS Tenant ID must be a valid UUID."))

    @api.constrains("elmogps_tenant_id", "company_id")
    def _check_unique_tenant_id(self):
        for partner in self:
            if not partner.elmogps_tenant_id:
                continue
            duplicate = self.search_count(
                [
                    ("id", "!=", partner.id),
                    ("elmogps_tenant_id", "=", partner.elmogps_tenant_id),
                ]
            )
            if duplicate:
                raise ValidationError(_("ELMOGPS Tenant ID must be unique."))

    def action_activate_elmogps_customer(self):
        for partner in self:
            partner.write(
                {
                    "is_elmogps_customer": True,
                    "elmogps_service_status": "active",
                    "elmogps_activation_date": fields.Date.context_today(partner),
                    "elmogps_suspension_date": False,
                }
            )
            self.env["elmogps.integration.event"].sudo().create_event(
                "customer.activated",
                partner,
                self.env["elmogps.integration.payload.builder"].build_customer_payload(partner),
            )

    def action_suspend_elmogps_customer(self):
        for partner in self:
            partner.write(
                {
                    "elmogps_service_status": "suspended",
                    "elmogps_suspension_date": fields.Date.context_today(partner),
                }
            )
            self.env["elmogps.integration.event"].sudo().create_event(
                "customer.suspended",
                partner,
                self.env["elmogps.integration.payload.builder"].build_customer_payload(partner),
            )

    def action_view_elmogps_contracts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("ELMOGPS Contracts"),
            "res_model": "elmogps.contract",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_view_elmogps_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "elmogps.installation",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_view_elmogps_vehicles(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Vehicles"),
            "res_model": "elmogps.vehicle.reference",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }

    def action_view_elmogps_devices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("GPS Devices"),
            "res_model": "stock.lot",
            "view_mode": "list,form",
            "domain": [
                ("elmogps_asset_type", "=", "gps_device"),
                ("elmogps_customer_id", "=", self.id),
            ],
        }

    def write(self, vals):
        track_fields = {
            "name",
            "email",
            "phone",
            "elmogps_service_status",
            "elmogps_vehicle_limit",
            "elmogps_tenant_id",
        }
        res = super().write(vals)
        if track_fields.intersection(vals.keys()):
            for partner in self.filtered("is_elmogps_customer"):
                if partner.elmogps_service_status == "active":
                    self.env["elmogps.integration.event"].sudo().create_event(
                        "customer.updated",
                        partner,
                        self.env["elmogps.integration.payload.builder"].build_customer_payload(
                            partner
                        ),
                    )
        return res
