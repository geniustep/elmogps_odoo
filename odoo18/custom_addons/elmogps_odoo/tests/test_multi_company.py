from odoo.tests import tagged

from odoo.addons.elmogps_odoo.tests.common import ElmogpsTestCommon


@tagged("post_install", "-at_install")
class TestElmogpsMultiCompany(ElmogpsTestCommon):

    def test_contract_company_isolation(self):
        company_b = self.env["res.company"].create({"name": "ELMOGPS Branch B"})
        partner_b = self.env["res.partner"].create(
            {
                "name": "Branch B Customer",
                "company_id": company_b.id,
                "is_elmogps_customer": True,
            }
        )
        contract_b = self.env["elmogps.contract"].with_company(company_b).create(
            {
                "partner_id": partner_b.id,
                "company_id": company_b.id,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "vehicle_limit": 3,
            }
        )
        contracts = (
            self.env["elmogps.contract"]
            .with_user(self.elmogps_user)
            .with_company(self.env.company)
            .search([("id", "=", contract_b.id)])
        )
        self.assertFalse(contracts)
