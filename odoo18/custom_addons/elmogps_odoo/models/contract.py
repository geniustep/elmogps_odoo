import re

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

CONTRACT_STATUSES = [
    ("draft", "Draft"),
    ("confirmed", "Confirmed"),
    ("active", "Active"),
    ("suspended", "Suspended"),
    ("expired", "Expired"),
    ("cancelled", "Cancelled"),
]

BILLING_PERIODS = [
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("yearly", "Yearly"),
]


class ElmogpsContract(models.Model):
    _name = "elmogps.contract"
    _description = "ELMOGPS Service Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, default="New", index=True)
    sequence = fields.Integer(default=10)
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
    sale_order_id = fields.Many2one("sale.order", string="Sale Order")
    subscription_product_id = fields.Many2one(
        "product.product",
        string="Subscription Product",
        domain="[('elmogps_product_type', '=', 'subscription_service')]",
    )
    start_date = fields.Date(string="Start Date", tracking=True)
    end_date = fields.Date(string="End Date", tracking=True)
    status = fields.Selection(
        selection=CONTRACT_STATUSES,
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    billing_period = fields.Selection(
        selection=BILLING_PERIODS,
        string="Billing Period",
        default="monthly",
    )
    vehicle_limit = fields.Integer(string="Vehicle Limit", default=1, tracking=True)
    grace_days = fields.Integer(string="Grace Days", default=0)
    auto_renew = fields.Boolean(string="Auto Renew", default=False)
    next_renewal_date = fields.Date(string="Next Renewal Date")
    activation_date = fields.Date(string="Activation Date")
    suspension_date = fields.Date(string="Suspension Date")
    cancellation_date = fields.Date(string="Cancellation Date")
    odoo_subscription_reference = fields.Char(string="Odoo Subscription Reference")
    elmogps_tenant_id = fields.Char(string="ELMOGPS Tenant ID", copy=False, index=True)
    notes = fields.Html(string="Notes")
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    recurring_amount = fields.Monetary(string="Recurring Amount", currency_field="currency_id")
    active = fields.Boolean(default=True)
    allow_vehicle_limit_override = fields.Boolean(
        string="Allow Vehicle Limit Override",
        help="Permits installations beyond the vehicle limit.",
    )

    installation_ids = fields.One2many("elmogps.installation", "contract_id", string="Installations")
    installation_count = fields.Integer(compute="_compute_installation_count")
    active_installation_count = fields.Integer(compute="_compute_installation_count")

    @api.depends("installation_ids", "installation_ids.status")
    def _compute_installation_count(self):
        for contract in self:
            contract.installation_count = len(contract.installation_ids)
            contract.active_installation_count = len(
                contract.installation_ids.filtered(lambda i: i.status == "completed")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("elmogps.contract") or "New"
        return super().create(vals_list)

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        for contract in self:
            if contract.start_date and contract.end_date and contract.end_date < contract.start_date:
                raise ValidationError(_("End date must be after start date."))

    @api.constrains("elmogps_tenant_id")
    def _check_tenant_id(self):
        for contract in self:
            if contract.elmogps_tenant_id and not UUID_PATTERN.match(contract.elmogps_tenant_id):
                raise ValidationError(_("ELMOGPS Tenant ID must be a valid UUID."))

    @api.constrains("partner_id", "company_id")
    def _check_partner_company(self):
        for contract in self:
            if contract.partner_id.company_id and contract.partner_id.company_id != contract.company_id:
                raise ValidationError(_("Customer company must match contract company."))

    def _validate_activation_requirements(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("A customer is required to activate the contract."))
        if not self.start_date or not self.end_date:
            raise UserError(_("Start and end dates are required to activate the contract."))
        if not self.vehicle_limit:
            raise UserError(_("Vehicle limit is required to activate the contract."))

    def action_confirm(self):
        for contract in self:
            if not contract.partner_id:
                raise UserError(_("A customer is required."))
            contract.status = "confirmed"

    def action_activate(self):
        for contract in self:
            contract._validate_activation_requirements()
            contract.write(
                {
                    "status": "active",
                    "activation_date": fields.Date.context_today(contract),
                }
            )
            if contract.partner_id.elmogps_service_status != "active":
                contract.partner_id.action_activate_elmogps_customer()
            self.env["elmogps.integration.event"].sudo().create_event(
                "subscription.activated",
                contract,
                self.env["elmogps.integration.payload.builder"].build_contract_payload(contract),
            )

    def action_suspend(self):
        builder = self.env["elmogps.integration.payload.builder"]
        for contract in self:
            contract.write(
                {
                    "status": "suspended",
                    "suspension_date": fields.Date.context_today(contract),
                }
            )
            self.env["elmogps.integration.event"].sudo().create_event(
                "subscription.changed",
                contract,
                builder.build_subscription_payload(contract),
            )

    def action_expire(self):
        for contract in self:
            contract.status = "expired"
            self.env["elmogps.integration.event"].sudo().create_event(
                "subscription.expired",
                contract,
                self.env["elmogps.integration.payload.builder"].build_contract_payload(contract),
            )

    def action_cancel(self):
        for contract in self:
            contract.write(
                {
                    "status": "cancelled",
                    "cancellation_date": fields.Date.context_today(contract),
                }
            )
            self.env["elmogps.integration.event"].sudo().create_event(
                "subscription.cancelled",
                contract,
                self.env["elmogps.integration.payload.builder"].build_contract_payload(contract),
            )

    def action_renew(self):
        for contract in self:
            if not contract.end_date:
                raise UserError(_("End date is required for renewal."))
            new_end = contract.end_date + relativedelta(years=1)
            contract.write(
                {
                    "end_date": new_end,
                    "next_renewal_date": new_end,
                    "status": "active",
                }
            )
            self.env["elmogps.integration.event"].sudo().create_event(
                "subscription.renewed",
                contract,
                self.env["elmogps.integration.payload.builder"].build_contract_payload(contract),
            )

    def check_vehicle_limit(self, extra=0):
        self.ensure_one()
        if self.allow_vehicle_limit_override:
            return True
        active_count = self.env["elmogps.installation"].search_count(
            [
                ("contract_id", "=", self.id),
                ("status", "=", "completed"),
            ]
        )
        return (active_count + extra) <= self.vehicle_limit

    def action_view_installations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Installations"),
            "res_model": "elmogps.installation",
            "view_mode": "list,form",
            "domain": [("contract_id", "=", self.id)],
            "context": {"default_contract_id": self.id, "default_partner_id": self.partner_id.id},
        }
