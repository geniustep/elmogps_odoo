import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

IMEI_PATTERN = re.compile(r"^\d{15}$")
ICCID_PATTERN = re.compile(r"^\d{19,20}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

OPERATIONAL_STATUSES = [
    ("in_stock", "In Stock"),
    ("reserved", "Reserved"),
    ("allocated", "Allocated"),
    ("installed", "Installed"),
    ("maintenance", "Maintenance"),
    ("repair", "Repair"),
    ("returned", "Returned"),
    ("retired", "Retired"),
    ("lost", "Lost"),
]


def normalize_identifier(value):
    if not value:
        return value
    return re.sub(r"[\s\-]", "", str(value).strip())


class StockLot(models.Model):
    _inherit = "stock.lot"

    elmogps_asset_type = fields.Selection(
        selection=[
            ("gps_device", "GPS Device"),
            ("sim_card", "SIM Card"),
            ("accessory", "Accessory"),
        ],
        string="ELMOGPS Asset Type",
        index=True,
    )
    elmogps_imei = fields.Char(string="IMEI", index=True, copy=False)
    elmogps_iccid = fields.Char(string="ICCID", index=True, copy=False)
    elmogps_phone_number = fields.Char(string="Phone Number")
    elmogps_operator = fields.Char(string="Operator")
    elmogps_apn = fields.Char(string="APN")
    elmogps_device_model = fields.Char(string="Device Model")
    elmogps_firmware_version = fields.Char(string="Firmware Version")
    elmogps_traccar_device_id = fields.Char(string="Traccar Device ID", copy=False)
    elmogps_device_id = fields.Char(string="ELMOGPS Device ID", copy=False, index=True)
    elmogps_operational_status = fields.Selection(
        selection=OPERATIONAL_STATUSES,
        string="Operational Status",
        default="in_stock",
        tracking=True,
        index=True,
    )
    elmogps_warranty_start = fields.Date(string="Warranty Start")
    elmogps_warranty_end = fields.Date(string="Warranty End")
    elmogps_last_sync_at = fields.Datetime(string="Last Sync At")
    elmogps_customer_id = fields.Many2one("res.partner", string="Customer", index=True)
    elmogps_active_installation_id = fields.Many2one(
        "elmogps.installation",
        string="Active Installation",
        copy=False,
    )
    elmogps_active_gps_lot_id = fields.Many2one(
        "stock.lot",
        string="Linked GPS Device",
        copy=False,
        help="For SIM cards: the GPS device this SIM is currently linked to.",
    )

    _sql_constraints = [
        (
            "elmogps_imei_unique",
            "UNIQUE(elmogps_imei)",
            "IMEI must be unique when set.",
        ),
        (
            "elmogps_iccid_unique",
            "UNIQUE(elmogps_iccid)",
            "ICCID must be unique when set.",
        ),
        (
            "elmogps_device_id_unique",
            "UNIQUE(elmogps_device_id)",
            "ELMOGPS Device ID must be unique when set.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("elmogps_imei"):
                vals["elmogps_imei"] = normalize_identifier(vals["elmogps_imei"])
            if vals.get("elmogps_iccid"):
                vals["elmogps_iccid"] = normalize_identifier(vals["elmogps_iccid"])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("elmogps_imei"):
            vals["elmogps_imei"] = normalize_identifier(vals["elmogps_imei"])
        if vals.get("elmogps_iccid"):
            vals["elmogps_iccid"] = normalize_identifier(vals["elmogps_iccid"])
        return super().write(vals)

    @api.constrains("elmogps_asset_type", "elmogps_imei")
    def _check_imei(self):
        for lot in self:
            if lot.elmogps_asset_type != "gps_device":
                continue
            if not lot.elmogps_imei:
                raise ValidationError(_("GPS devices require a valid IMEI."))
            if not IMEI_PATTERN.match(lot.elmogps_imei):
                raise ValidationError(_("IMEI must be exactly 15 digits."))

    @api.constrains("elmogps_asset_type", "elmogps_iccid")
    def _check_iccid(self):
        for lot in self:
            if lot.elmogps_asset_type != "sim_card":
                continue
            if lot.elmogps_iccid and not ICCID_PATTERN.match(lot.elmogps_iccid):
                raise ValidationError(_("ICCID must be 19 or 20 digits."))

    @api.constrains("elmogps_device_id")
    def _check_device_id_uuid(self):
        for lot in self:
            if lot.elmogps_device_id and not UUID_PATTERN.match(lot.elmogps_device_id):
                raise ValidationError(_("ELMOGPS Device ID must be a valid UUID."))

    @api.constrains("elmogps_active_gps_lot_id", "elmogps_asset_type", "elmogps_operational_status")
    def _check_sim_single_device(self):
        for lot in self.filtered(
            lambda l: l.elmogps_asset_type == "sim_card"
            and l.elmogps_operational_status in ("allocated", "installed")
        ):
            duplicate = self.search_count(
                [
                    ("id", "!=", lot.id),
                    ("elmogps_asset_type", "=", "sim_card"),
                    ("elmogps_active_gps_lot_id", "=", lot.elmogps_active_gps_lot_id.id),
                    ("elmogps_operational_status", "in", ("allocated", "installed")),
                ]
            )
            if duplicate:
                raise ValidationError(
                    _("An active SIM cannot be linked to more than one GPS device.")
                )

    def action_allocate_device(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Allocate Device"),
            "res_model": "elmogps.allocate.device.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_lot_id": self.id},
        }

    def action_return_to_stock(self):
        builder = self.env["elmogps.integration.payload.builder"]
        for lot in self:
            lot.write(
                {
                    "elmogps_operational_status": "in_stock",
                    "elmogps_customer_id": False,
                    "elmogps_active_installation_id": False,
                    "elmogps_active_gps_lot_id": False,
                }
            )
            if lot.elmogps_asset_type == "gps_device":
                payload = builder.build_device_released_payload(lot)
                event_type = "device.released"
            elif lot.elmogps_asset_type == "sim_card":
                payload = builder.build_sim_released_payload(lot)
                event_type = "sim.released"
            else:
                continue
            self.env["elmogps.integration.event"].sudo().create_event(
                event_type, lot, payload
            )
