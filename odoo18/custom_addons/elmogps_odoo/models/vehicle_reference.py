import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class ElmogpsVehicleReference(models.Model):
    _name = "elmogps.vehicle.reference"
    _description = "ELMOGPS Vehicle Reference"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "plate_number, id"

    name = fields.Char(string="Name", required=True, index=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    plate_number = fields.Char(string="Plate Number", required=True, index=True)
    vin = fields.Char(string="VIN", index=True)
    brand = fields.Char(string="Brand")
    model = fields.Char(string="Model")
    model_year = fields.Char(string="Model Year")
    vehicle_type = fields.Selection(
        selection=[
            ("car", "Car"),
            ("truck", "Truck"),
            ("van", "Van"),
            ("bus", "Bus"),
            ("motorcycle", "Motorcycle"),
            ("other", "Other"),
        ],
        string="Vehicle Type",
        default="car",
    )
    elmogps_vehicle_id = fields.Char(string="ELMOGPS Vehicle ID", copy=False, index=True)
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Notes")

    installation_ids = fields.One2many("elmogps.installation", "vehicle_id", string="Installations")
    maintenance_ids = fields.One2many(
        "maintenance.request", "elmogps_vehicle_id", string="Maintenance"
    )
    installation_count = fields.Integer(compute="_compute_counts")
    maintenance_count = fields.Integer(compute="_compute_counts")

    _sql_constraints = [
        (
            "plate_unique_per_partner",
            "UNIQUE(partner_id, plate_number, company_id)",
            "Plate number must be unique per customer and company.",
        ),
        (
            "vin_unique",
            "UNIQUE(vin)",
            "VIN must be unique when set.",
        ),
        (
            "elmogps_vehicle_id_unique",
            "UNIQUE(elmogps_vehicle_id)",
            "ELMOGPS Vehicle ID must be unique when set.",
        ),
    ]

    @api.depends("installation_ids", "maintenance_ids")
    def _compute_counts(self):
        for vehicle in self:
            vehicle.installation_count = len(vehicle.installation_ids)
            vehicle.maintenance_count = len(vehicle.maintenance_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name"):
                plate = vals.get("plate_number", "")
                vals["name"] = plate or self.env["ir.sequence"].next_by_code(
                    "elmogps.vehicle.reference"
                )
        return super().create(vals_list)

    @api.constrains("elmogps_vehicle_id")
    def _check_vehicle_id_uuid(self):
        for vehicle in self:
            if vehicle.elmogps_vehicle_id and not UUID_PATTERN.match(vehicle.elmogps_vehicle_id):
                raise ValidationError(_("ELMOGPS Vehicle ID must be a valid UUID."))

    def action_view_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "elmogps.installation",
            "view_mode": "list,form",
            "domain": [("vehicle_id", "=", self.id)],
            "context": {"default_vehicle_id": self.id, "default_partner_id": self.partner_id.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Maintenance"),
            "res_model": "maintenance.request",
            "view_mode": "list,form",
            "domain": [("elmogps_vehicle_id", "=", self.id)],
        }
