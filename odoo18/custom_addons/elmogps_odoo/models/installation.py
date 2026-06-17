import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

INSTALLATION_STATUSES = [
    ("draft", "Draft"),
    ("scheduled", "Scheduled"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("removed", "Removed"),
    ("cancelled", "Cancelled"),
]

INSTALLATION_TYPES = [
    ("new_installation", "New Installation"),
    ("replacement", "Replacement"),
    ("transfer", "Transfer"),
    ("removal", "Removal"),
    ("maintenance_reinstall", "Maintenance Reinstall"),
]

SYNC_STATUSES = [
    ("pending", "Pending"),
    ("synced", "Synced"),
    ("failed", "Failed"),
]


class ElmogpsInstallation(models.Model):
    _name = "elmogps.installation"
    _description = "ELMOGPS Installation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "scheduled_at desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, default="New", index=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        tracking=True,
        index=True,
    )
    contract_id = fields.Many2one(
        "elmogps.contract",
        string="Contract",
        domain="[('partner_id', '=', partner_id), ('status', 'in', ('confirmed', 'active'))]",
        index=True,
    )
    sale_order_id = fields.Many2one("sale.order", string="Sale Order")
    vehicle_id = fields.Many2one(
        "elmogps.vehicle.reference",
        string="Vehicle",
        domain="[('partner_id', '=', partner_id)]",
        index=True,
    )
    gps_lot_id = fields.Many2one(
        "stock.lot",
        string="GPS Device",
        domain="[('elmogps_asset_type', '=', 'gps_device')]",
        index=True,
    )
    sim_lot_id = fields.Many2one(
        "stock.lot",
        string="SIM Card",
        domain="[('elmogps_asset_type', '=', 'sim_card')]",
        index=True,
    )
    technician_id = fields.Many2one(
        "res.users",
        string="Technician",
        domain="[('share', '=', False)]",
        index=True,
    )
    scheduled_at = fields.Datetime(string="Scheduled At", tracking=True)
    started_at = fields.Datetime(string="Started At")
    completed_at = fields.Datetime(string="Completed At", tracking=True)
    removed_at = fields.Datetime(string="Removed At", tracking=True)
    installation_location = fields.Char(string="Installation Location")
    installation_type = fields.Selection(
        selection=INSTALLATION_TYPES,
        string="Installation Type",
        default="new_installation",
        required=True,
    )
    status = fields.Selection(
        selection=INSTALLATION_STATUSES,
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    notes = fields.Html(string="Notes")
    elmogps_installation_id = fields.Char(string="ELMOGPS Installation ID", copy=False, index=True)
    elmogps_assignment_id = fields.Char(string="ELMOGPS Assignment ID", copy=False)
    sync_status = fields.Selection(
        selection=SYNC_STATUSES,
        string="Sync Status",
        default="pending",
    )
    skip_contract_check = fields.Boolean(
        string="Skip Contract Check",
        help="Authorized exception when no active contract is available.",
    )
    requires_sim = fields.Boolean(compute="_compute_requires_sim", store=True)

    @api.depends("gps_lot_id", "gps_lot_id.product_id.elmogps_requires_sim")
    def _compute_requires_sim(self):
        for inst in self:
            product = inst.gps_lot_id.product_id if inst.gps_lot_id else False
            inst.requires_sim = bool(product and product.elmogps_requires_sim)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("elmogps.installation") or "New"
        return super().create(vals_list)

    @api.constrains("elmogps_installation_id")
    def _check_installation_id_uuid(self):
        for inst in self:
            if inst.elmogps_installation_id and not UUID_PATTERN.match(inst.elmogps_installation_id):
                raise ValidationError(_("ELMOGPS Installation ID must be a valid UUID."))

    @api.constrains("partner_id", "company_id", "contract_id", "vehicle_id", "gps_lot_id")
    def _check_company_consistency(self):
        for inst in self:
            if inst.contract_id and inst.contract_id.company_id != inst.company_id:
                raise ValidationError(_("Contract company must match installation company."))
            if inst.vehicle_id and inst.vehicle_id.company_id != inst.company_id:
                raise ValidationError(_("Vehicle company must match installation company."))

    @api.constrains("gps_lot_id", "status")
    def _check_single_active_device(self):
        for inst in self.filtered(lambda i: i.status == "completed" and i.gps_lot_id):
            duplicate = self.search_count(
                [
                    ("id", "!=", inst.id),
                    ("gps_lot_id", "=", inst.gps_lot_id.id),
                    ("status", "=", "completed"),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("A GPS device cannot be actively installed on multiple vehicles.")
                )

    def action_schedule(self):
        for inst in self:
            if not inst.scheduled_at:
                raise UserError(_("Scheduled date is required."))
            inst.status = "scheduled"

    def action_start(self):
        for inst in self:
            inst.write(
                {
                    "status": "in_progress",
                    "started_at": fields.Datetime.now(),
                }
            )

    def _validate_completion(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("Customer is required to complete installation."))
        if not self.skip_contract_check:
            if not self.contract_id or self.contract_id.status != "active":
                raise UserError(_("An active contract is required to complete installation."))
            if not self.contract_id.check_vehicle_limit(extra=1):
                raise UserError(_("Vehicle limit exceeded for this contract."))
        if not self.vehicle_id:
            raise UserError(_("Vehicle is required to complete installation."))
        if not self.gps_lot_id:
            raise UserError(_("GPS device is required to complete installation."))
        if not self.gps_lot_id.elmogps_imei:
            raise UserError(_("A valid IMEI is required to complete installation."))
        if not self.technician_id:
            raise UserError(_("Technician is required to complete installation."))
        if self.requires_sim and not self.sim_lot_id:
            raise UserError(_("SIM card is required for this GPS device product."))
        active_on_other = self.search_count(
            [
                ("id", "!=", self.id),
                ("gps_lot_id", "=", self.gps_lot_id.id),
                ("status", "=", "completed"),
            ]
        )
        if active_on_other:
            raise UserError(_("This GPS device is already installed on another vehicle."))

    def action_complete(self):
        for inst in self:
            inst._validate_completion()
            completed_at = fields.Datetime.now()
            inst.write(
                {
                    "status": "completed",
                    "completed_at": completed_at,
                    "sync_status": "pending",
                }
            )
            inst.gps_lot_id.write(
                {
                    "elmogps_operational_status": "installed",
                    "elmogps_customer_id": inst.partner_id.id,
                    "elmogps_active_installation_id": inst.id,
                }
            )
            if inst.sim_lot_id:
                inst.sim_lot_id.write(
                    {
                        "elmogps_operational_status": "installed",
                        "elmogps_customer_id": inst.partner_id.id,
                        "elmogps_active_gps_lot_id": inst.gps_lot_id.id,
                        "elmogps_active_installation_id": inst.id,
                    }
                )
            builder = self.env["elmogps.integration.payload.builder"]
            self.env["elmogps.integration.event"].sudo().create_event(
                "installation.completed",
                inst,
                builder.build_installation_completed_payload(inst),
            )

    def action_remove(self):
        for inst in self:
            if inst.status != "completed":
                raise UserError(_("Only completed installations can be removed."))
            removed_at = fields.Datetime.now()
            inst.write(
                {
                    "status": "removed",
                    "removed_at": removed_at,
                }
            )
            if inst.gps_lot_id:
                inst.gps_lot_id.write(
                    {
                        "elmogps_operational_status": "returned",
                        "elmogps_active_installation_id": False,
                    }
                )
            if inst.sim_lot_id:
                inst.sim_lot_id.write(
                    {
                        "elmogps_operational_status": "returned",
                        "elmogps_active_gps_lot_id": False,
                        "elmogps_active_installation_id": False,
                    }
                )
            builder = self.env["elmogps.integration.payload.builder"]
            self.env["elmogps.integration.event"].sudo().create_event(
                "installation.removed",
                inst,
                builder.build_installation_removed_payload(inst),
            )

    def action_cancel(self):
        for inst in self:
            if inst.status == "completed":
                raise UserError(_("Completed installations cannot be cancelled. Use removal instead."))
            inst.status = "cancelled"

    def action_open_complete_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Complete Installation"),
            "res_model": "elmogps.complete.installation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_installation_id": self.id},
        }

    def action_open_remove_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Remove Device"),
            "res_model": "elmogps.remove.device.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_installation_id": self.id},
        }

    def action_transfer_device(self):
        self.ensure_one()
        if self.status != "completed":
            raise UserError(_("Only completed installations can be transferred."))
        new_vehicle = self.env.context.get("default_vehicle_id")
        return {
            "type": "ir.actions.act_window",
            "name": _("Transfer Device"),
            "res_model": "elmogps.installation",
            "view_mode": "form",
            "target": "current",
            "context": {
                "default_partner_id": self.partner_id.id,
                "default_contract_id": self.contract_id.id,
                "default_gps_lot_id": self.gps_lot_id.id,
                "default_sim_lot_id": self.sim_lot_id.id,
                "default_installation_type": "transfer",
                "default_vehicle_id": new_vehicle,
                "default_company_id": self.company_id.id,
            },
        }
