from odoo import fields, models


class ElmogpsCompleteInstallationWizard(models.TransientModel):
    _name = "elmogps.complete.installation.wizard"
    _description = "Complete Installation Wizard"

    installation_id = fields.Many2one(
        "elmogps.installation",
        string="Installation",
        required=True,
    )
    confirm = fields.Boolean(string="Confirm Completion", default=False)

    def action_confirm_complete(self):
        self.ensure_one()
        self.installation_id.action_complete()
        return {"type": "ir.actions.act_window_close"}
