# ELMOGPS Odoo Module

All-in-one Odoo 18 add-on for ELMOGPS commercial and operational management.

## Purpose

`elmogps_odoo` manages ELMOGPS customers, service contracts, GPS devices, SIM cards,
installations, maintenance, and outbound integration events (Outbox) from Odoo as the
commercial source of truth.

## Requirements

- Odoo 18.0 Community
- PostgreSQL
- Python dependencies: `requests` (for webhook delivery when integration is enabled)

## Dependencies

- `base`, `mail`, `contacts`, `sale_management`, `stock`, `purchase`, `account`, `maintenance`

Optional enterprise modules (`sale_subscription`, `industry_fsm`, `helpdesk`) are **not** required.

## Installation

1. Clone this repository and add the add-ons path to Odoo:

```bash
addons_path = ...,/path/to/elmogps_odoo/odoo18/custom_addons
```

2. Install the module on your database:

```bash
odoo-bin -d YOUR_DB -i elmogps_odoo --stop-after-init
```

3. Assign users to ELMOGPS security groups under Settings → Users.

## Security Groups

| Group | Scope |
|-------|-------|
| User | Limited read access |
| Sales | Customers, contracts, sale orders |
| Inventory | GPS devices, SIM cards, stock operations |
| Technician | Assigned installations and maintenance |
| Manager | Full ELMOGPS commercial/operational management |
| Integration Admin | Integration settings, outbox, logs |

## Models

| Model | Type | Description |
|-------|------|-------------|
| `res.partner` | extension | ELMOGPS customer fields |
| `product.template` | extension | ELMOGPS product classification |
| `stock.lot` | extension | GPS devices and SIM cards |
| `elmogps.contract` | new | Service contracts |
| `elmogps.vehicle.reference` | new | Commercial vehicle reference |
| `elmogps.installation` | new | Installation/removal workflow |
| `maintenance.request` | extension | ELMOGPS maintenance fields |
| `elmogps.integration.event` | new | Outbox events |
| `elmogps.integration.log` | new | Delivery logs |

## Workflows

- Customer activation/suspension → outbox events
- Contract lifecycle: draft → confirmed → active → suspended/expired/cancelled
- Device/SIM allocation and return to stock
- Installation: schedule → start → complete → remove/transfer
- Maintenance open/close events
- Outbox cron processes pending events when integration is enabled

## Integration Settings

Configure under **ELMOGPS → Configuration** (Integration Admin only):

- Integration enabled (default: **disabled**)
- API base URL
- Environment: disabled / development / staging / production
- Webhook timeout, max attempts, replay window, batch size

### Environment Variable

```bash
export ELMOGPS_ODOO_WEBHOOK_SECRET="your-hmac-secret"
```

The secret is never stored in Git or displayed in the UI.

## Webhook Events

Supported outbound event types:

- `customer.activated`, `customer.updated`, `customer.suspended`
- `subscription.activated`, `subscription.renewed`, `subscription.changed`, `subscription.expired`, `subscription.cancelled`
- `device.allocated`, `device.released`
- `sim.allocated`, `sim.released`
- `installation.completed`, `installation.removed`
- `maintenance.opened`, `maintenance.closed`

Headers: `X-ELMOGPS-Event-Id`, `X-ELMOGPS-Timestamp`, `X-ELMOGPS-Signature`, `X-ELMOGPS-Event-Version`

## Cron

`ELMOGPS: Process Outbox Events` runs every minute when integration is enabled.

## Tests

```bash
odoo-bin -d YOUR_DB -u elmogps_odoo --test-enable --test-tags /elmogps_odoo --stop-after-init
```

## Source of Truth Boundaries

| Domain | Odoo | ELMOGPS | Traccar |
|--------|------|---------|---------|
| Customers, contracts, billing | ✓ | | |
| Tenants, fleets, live tracking | | ✓ | |
| Raw GPS protocol/positions | | | ✓ |

Odoo does **not** connect directly to ELMOGPS or Traccar databases. Integration is via HTTPS webhooks and Outbox.

## Deferred

- Production ELMOGPS API calls (disabled by default)
- Tenant provisioning in ELMOGPS
- Bidirectional sync, SSO, maps, alerts
- External queues (Redis, etc.)

## Secrets Policy

Never commit `.env`, webhook secrets, or production credentials to Git.
