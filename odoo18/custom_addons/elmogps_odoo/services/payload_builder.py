from datetime import datetime, timezone

from odoo import models

from .integration_contract import CONTRACT_TO_SUBSCRIPTION_STATUS, date_to_iso_datetime


class ElmogpsIntegrationPayloadBuilder(models.AbstractModel):
    _name = "elmogps.integration.payload.builder"
    _description = "ELMOGPS Integration Payload Builder"

    def _partner_country_code(self, partner):
        return partner.country_id.code if partner.country_id else None

    def _partner_language(self, partner):
        return partner.lang or None

    def _partner_timezone(self, partner):
        return partner.tz or None

    def _tenant_id(self, record):
        tenant = getattr(record, "elmogps_tenant_id", None)
        if tenant:
            return tenant
        partner = getattr(record, "partner_id", None)
        if partner and partner.elmogps_tenant_id:
            return partner.elmogps_tenant_id
        return None

    def build_customer_payload(self, partner, *, status=None, reason_code=None, effective_at=None):
        payload = {
            "odoo_partner_id": partner.id,
            "customer_code": partner.elmogps_customer_code or None,
            "name": partner.name,
            "status": status or partner.elmogps_service_status,
            "vehicle_limit": partner.elmogps_vehicle_limit,
            "email": partner.email or None,
            "phone": partner.phone or None,
            "country_code": self._partner_country_code(partner),
            "timezone": self._partner_timezone(partner),
            "language": self._partner_language(partner),
            "elmogps_tenant_id": partner.elmogps_tenant_id or None,
        }
        if reason_code:
            payload["reason_code"] = reason_code
        if effective_at:
            payload["effective_at"] = effective_at
        return payload

    def build_customer_activated_payload(self, partner):
        return self.build_customer_payload(partner, status="active")

    def build_customer_updated_payload(self, partner):
        return self.build_customer_payload(partner)

    def build_customer_suspended_payload(self, partner, reason_code="manual"):
        effective = partner.elmogps_suspension_date
        effective_at = date_to_iso_datetime(effective) if effective else datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.build_customer_payload(
            partner,
            status="suspended",
            reason_code=reason_code,
            effective_at=effective_at,
        )

    def build_subscription_payload(self, contract):
        status = CONTRACT_TO_SUBSCRIPTION_STATUS.get(contract.status, contract.status)
        grace_ends = None
        if contract.end_date and contract.grace_days:
            from datetime import timedelta

            grace_date = contract.end_date + timedelta(days=contract.grace_days)
            grace_ends = date_to_iso_datetime(grace_date)
        return {
            "odoo_contract_id": contract.id,
            "odoo_partner_id": contract.partner_id.id,
            "elmogps_tenant_id": contract.elmogps_tenant_id or self._tenant_id(contract.partner_id),
            "status": status,
            "vehicle_limit": contract.vehicle_limit,
            "enabled_features": [],
            "starts_at": date_to_iso_datetime(contract.start_date),
            "ends_at": date_to_iso_datetime(contract.end_date),
            "grace_ends_at": grace_ends,
            "auto_renew": bool(contract.auto_renew),
        }

    def build_contract_payload(self, contract):
        return self.build_subscription_payload(contract)

    def build_device_allocated_payload(self, lot, contract=None):
        return {
            "odoo_stock_lot_id": lot.id,
            "odoo_partner_id": lot.elmogps_customer_id.id if lot.elmogps_customer_id else None,
            "odoo_contract_id": contract.id if contract else None,
            "elmogps_tenant_id": self._tenant_id(lot.elmogps_customer_id) if lot.elmogps_customer_id else None,
            "imei": lot.elmogps_imei or None,
            "serial_number": lot.name,
            "device_model": lot.elmogps_device_model or None,
            "product_id": lot.product_id.id if lot.product_id else None,
            "traccar_device_id": lot.elmogps_traccar_device_id or None,
            "operational_status": lot.elmogps_operational_status,
        }

    def build_device_released_payload(self, lot, reason_code="removed"):
        return {
            "odoo_stock_lot_id": lot.id,
            "elmogps_device_id": lot.elmogps_device_id or None,
            "imei": lot.elmogps_imei or None,
            "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason_code": reason_code,
        }

    def build_sim_allocated_payload(self, lot, contract=None):
        return {
            "odoo_sim_lot_id": lot.id,
            "odoo_partner_id": lot.elmogps_customer_id.id if lot.elmogps_customer_id else None,
            "elmogps_tenant_id": self._tenant_id(lot.elmogps_customer_id) if lot.elmogps_customer_id else None,
            "iccid": lot.elmogps_iccid or None,
            "phone_number": lot.elmogps_phone_number or None,
            "operator_code": lot.elmogps_operator or None,
            "apn": lot.elmogps_apn or None,
            "status": "allocated",
            "odoo_contract_id": contract.id if contract else None,
        }

    def build_sim_released_payload(self, lot, reason_code="removed"):
        return {
            "odoo_sim_lot_id": lot.id,
            "iccid": lot.elmogps_iccid or None,
            "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason_code": reason_code,
        }

    def build_lot_payload(self, lot, contract=None):
        if lot.elmogps_asset_type == "gps_device":
            return self.build_device_allocated_payload(lot, contract=contract)
        if lot.elmogps_asset_type == "sim_card":
            return self.build_sim_allocated_payload(lot, contract=contract)
        return {
            "odoo_stock_lot_id": lot.id,
            "asset_type": lot.elmogps_asset_type,
            "operational_status": lot.elmogps_operational_status,
        }

    def _vehicle_block(self, vehicle):
        if not vehicle:
            return None
        return {
            "odoo_vehicle_reference_id": vehicle.id,
            "elmogps_vehicle_id": vehicle.elmogps_vehicle_id or None,
            "plate_number": vehicle.plate_number,
            "vin": vehicle.vin or None,
            "brand": vehicle.brand or None,
            "model": vehicle.model or None,
            "model_year": int(vehicle.model_year) if vehicle.model_year and str(vehicle.model_year).isdigit() else None,
            "vehicle_type": vehicle.vehicle_type or None,
        }

    def _device_block(self, lot):
        if not lot:
            return None
        return {
            "odoo_stock_lot_id": lot.id,
            "elmogps_device_id": lot.elmogps_device_id or None,
            "imei": lot.elmogps_imei or None,
            "device_model": lot.elmogps_device_model or None,
            "traccar_device_id": lot.elmogps_traccar_device_id or None,
        }

    def _sim_block(self, lot):
        if not lot:
            return None
        return {
            "odoo_sim_lot_id": lot.id,
            "iccid": lot.elmogps_iccid or None,
            "phone_number": lot.elmogps_phone_number or None,
            "operator_code": lot.elmogps_operator or None,
        }

    def build_installation_completed_payload(self, installation):
        return {
            "odoo_installation_id": installation.id,
            "odoo_partner_id": installation.partner_id.id,
            "odoo_contract_id": installation.contract_id.id if installation.contract_id else None,
            "elmogps_tenant_id": self._tenant_id(installation.partner_id),
            "installation_type": installation.installation_type,
            "completed_at": (
                installation.completed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if installation.completed_at
                else None
            ),
            "vehicle": self._vehicle_block(installation.vehicle_id),
            "device": self._device_block(installation.gps_lot_id),
            "sim": self._sim_block(installation.sim_lot_id),
            "odoo_technician_user_id": installation.technician_id.id
            if installation.technician_id
            else None,
        }

    def build_installation_removed_payload(self, installation, reason_code="transfer"):
        return {
            "odoo_installation_id": installation.id,
            "odoo_partner_id": installation.partner_id.id,
            "elmogps_tenant_id": self._tenant_id(installation.partner_id),
            "elmogps_assignment_id": None,
            "odoo_vehicle_reference_id": installation.vehicle_id.id if installation.vehicle_id else None,
            "odoo_stock_lot_id": installation.gps_lot_id.id if installation.gps_lot_id else None,
            "imei": installation.gps_lot_id.elmogps_imei if installation.gps_lot_id else None,
            "removed_at": (
                installation.removed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                if installation.removed_at
                else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ),
            "reason_code": reason_code,
            "return_device_to_stock": True,
        }

    def build_installation_payload(self, installation):
        if installation.status == "removed":
            return self.build_installation_removed_payload(installation)
        if installation.status == "completed":
            return self.build_installation_completed_payload(installation)
        return self.build_installation_completed_payload(installation)

    def build_maintenance_opened_payload(self, maintenance):
        return {
            "odoo_maintenance_id": maintenance.id,
            "odoo_partner_id": maintenance.elmogps_customer_id.id
            if maintenance.elmogps_customer_id
            else None,
            "odoo_installation_id": maintenance.elmogps_installation_id.id
            if maintenance.elmogps_installation_id
            else None,
            "odoo_stock_lot_id": maintenance.elmogps_device_lot_id.id
            if maintenance.elmogps_device_lot_id
            else None,
            "elmogps_tenant_id": self._tenant_id(maintenance.elmogps_customer_id)
            if maintenance.elmogps_customer_id
            else None,
            "elmogps_device_id": (
                maintenance.elmogps_device_lot_id.elmogps_device_id
                if maintenance.elmogps_device_lot_id
                else None
            ),
            "issue_type": maintenance.elmogps_issue_type,
            "opened_at": maintenance.create_date.strftime("%Y-%m-%dT%H:%M:%SZ")
            if maintenance.create_date
            else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "warranty_case": bool(maintenance.elmogps_warranty_case),
        }

    def build_maintenance_closed_payload(self, maintenance, resolution_code="other"):
        return {
            "odoo_maintenance_id": maintenance.id,
            "odoo_stock_lot_id": maintenance.elmogps_device_lot_id.id
            if maintenance.elmogps_device_lot_id
            else None,
            "elmogps_device_id": (
                maintenance.elmogps_device_lot_id.elmogps_device_id
                if maintenance.elmogps_device_lot_id
                else None
            ),
            "status": "closed",
            "resolution_code": resolution_code,
            "closed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def build_maintenance_payload(self, maintenance):
        if maintenance.archive or (maintenance.stage_id and maintenance.stage_id.done):
            return self.build_maintenance_closed_payload(maintenance)
        return self.build_maintenance_opened_payload(maintenance)
