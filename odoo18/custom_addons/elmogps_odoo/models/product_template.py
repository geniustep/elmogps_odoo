from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    elmogps_product_type = fields.Selection(
        selection=[
            ("none", "None"),
            ("gps_device", "GPS Device"),
            ("sim_card", "SIM Card"),
            ("installation_service", "Installation Service"),
            ("subscription_service", "Subscription Service"),
            ("maintenance_service", "Maintenance Service"),
            ("accessory", "Accessory"),
        ],
        string="ELMOGPS Product Type",
        default="none",
        index=True,
    )
    elmogps_device_model = fields.Char(string="Device Model")
    elmogps_protocol = fields.Char(string="Protocol")
    elmogps_default_warranty_months = fields.Integer(
        string="Default Warranty (months)", default=12
    )
    elmogps_requires_serial_tracking = fields.Boolean(
        string="Requires Serial Tracking",
        compute="_compute_elmogps_requires_serial_tracking",
        store=True,
    )
    elmogps_requires_sim = fields.Boolean(
        string="Requires SIM",
        help="GPS devices of this product require a SIM card at installation.",
    )

    @api.depends("elmogps_product_type", "tracking")
    def _compute_elmogps_requires_serial_tracking(self):
        for product in self:
            product.elmogps_requires_serial_tracking = product.elmogps_product_type in (
                "gps_device",
                "sim_card",
            )

    @api.constrains("elmogps_product_type", "tracking", "type")
    def _check_elmogps_product_rules(self):
        for product in self:
            if product.elmogps_product_type == "gps_device":
                if product.tracking != "serial":
                    raise ValidationError(
                        _("GPS device products must use serial number tracking.")
                    )
                if product.type != "consu" or not product.is_storable:
                    raise ValidationError(_("GPS device products must be storable goods."))
            if product.elmogps_product_type == "sim_card":
                if product.tracking != "serial":
                    raise ValidationError(
                        _("SIM card products must use serial number tracking.")
                    )
            if product.elmogps_product_type in (
                "installation_service",
                "subscription_service",
                "maintenance_service",
            ):
                if product.type != "service":
                    raise ValidationError(
                        _("ELMOGPS service products must be service type.")
                    )

    @api.onchange("elmogps_product_type")
    def _onchange_elmogps_product_type(self):
        if self.elmogps_product_type == "gps_device":
            self.tracking = "serial"
            self.type = "consu"
            self.is_storable = True
        elif self.elmogps_product_type == "sim_card":
            self.tracking = "serial"
            self.type = "consu"
            self.is_storable = True
        elif self.elmogps_product_type in (
            "installation_service",
            "subscription_service",
            "maintenance_service",
        ):
            self.type = "service"
