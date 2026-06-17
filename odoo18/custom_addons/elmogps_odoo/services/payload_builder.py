from odoo import models


class ElmogpsIntegrationPayloadBuilder(models.AbstractModel):
    _name = "elmogps.integration.payload.builder"
    _description = "ELMOGPS Integration Payload Builder"

    def build_customer_payload(self, partner):
        return {
            "odoo_partner_id": partner.id,
            "name": partner.name,
            "email": partner.email or None,
            "phone": partner.phone or None,
            "status": partner.elmogps_service_status,
            "vehicle_limit": partner.elmogps_vehicle_limit,
            "elmogps_tenant_id": partner.elmogps_tenant_id or None,
        }

    def build_contract_payload(self, contract):
        return {
            "odoo_contract_id": contract.id,
            "odoo_partner_id": contract.partner_id.id,
            "reference": contract.name,
            "status": contract.status,
            "start_date": contract.start_date.isoformat() if contract.start_date else None,
            "end_date": contract.end_date.isoformat() if contract.end_date else None,
            "vehicle_limit": contract.vehicle_limit,
            "recurring_amount": contract.recurring_amount,
            "billing_period": contract.billing_period,
        }

    def build_lot_payload(self, lot):
        return {
            "odoo_stock_lot_id": lot.id,
            "asset_type": lot.elmogps_asset_type,
            "imei": lot.elmogps_imei or None,
            "iccid": lot.elmogps_iccid or None,
            "operational_status": lot.elmogps_operational_status,
            "odoo_partner_id": lot.elmogps_customer_id.id if lot.elmogps_customer_id else None,
        }

    def build_installation_payload(self, installation):
        payload = {
            "odoo_partner_id": installation.partner_id.id,
            "odoo_contract_id": installation.contract_id.id if installation.contract_id else None,
            "odoo_installation_id": installation.id,
            "odoo_stock_lot_id": installation.gps_lot_id.id if installation.gps_lot_id else None,
            "imei": installation.gps_lot_id.elmogps_imei if installation.gps_lot_id else None,
            "status": installation.status,
            "installation_type": installation.installation_type,
            "completed_at": (
                installation.completed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if installation.completed_at
                else None
            ),
            "removed_at": (
                installation.removed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if installation.removed_at
                else None
            ),
        }
        if installation.sim_lot_id:
            payload["sim"] = {
                "odoo_stock_lot_id": installation.sim_lot_id.id,
                "iccid": installation.sim_lot_id.elmogps_iccid,
            }
        if installation.vehicle_id:
            payload["vehicle"] = {
                "odoo_vehicle_reference_id": installation.vehicle_id.id,
                "plate_number": installation.vehicle_id.plate_number,
                "vin": installation.vehicle_id.vin or None,
            }
        return payload

    def build_maintenance_payload(self, maintenance):
        return {
            "odoo_maintenance_id": maintenance.id,
            "odoo_partner_id": maintenance.elmogps_customer_id.id
            if maintenance.elmogps_customer_id
            else None,
            "issue_type": maintenance.elmogps_issue_type,
            "odoo_device_lot_id": maintenance.elmogps_device_lot_id.id
            if maintenance.elmogps_device_lot_id
            else None,
            "odoo_vehicle_reference_id": maintenance.elmogps_vehicle_id.id
            if maintenance.elmogps_vehicle_id
            else None,
            "warranty_case": maintenance.elmogps_warranty_case,
        }
