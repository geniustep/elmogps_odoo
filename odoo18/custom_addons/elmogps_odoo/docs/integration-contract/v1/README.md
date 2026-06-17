# ELMOGPS Odoo Integration Contract — v1

Contract name: **ELMOGPS Odoo Integration Contract — v1**  
Event version: **1**  
Odoo module: `elmogps_odoo` 18.0  
Direction: **Odoo → ELMOGPS Backend** (signed HTTPS webhooks)

## Architecture boundaries

| System | Role |
|--------|------|
| Odoo | Commercial, billing, inventory, installation source of truth |
| ELMOGPS Backend | Operational source of truth (tenants, vehicles, devices) |
| Traccar | Raw tracking source |

Odoo never connects directly to ELMOGPS or Traccar databases. Integration is outbound-only via signed webhooks after successful business transactions.

## Endpoint (documented, not activated from Odoo in v1)

```http
POST /api/v1/integrations/odoo/events
Content-Type: application/json
User-Agent: elmogps-odoo/18.0
```

Base URL remains **disabled** in Odoo until a dedicated activation task.

## Event envelope

Every outbound message uses this envelope:

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "installation.completed",
  "event_version": 1,
  "occurred_at": "2026-06-17T12:00:00Z",
  "source": "odoo",
  "odoo_company_id": 1,
  "payload": {}
}
```

| Field | Rules |
|-------|-------|
| `event_id` | UUID v4, unique, immutable across retries, idempotency key |
| `event_type` | Lowercase dot-separated value from supported list |
| `event_version` | Positive integer; current value `1` |
| `occurred_at` | UTC ISO-8601 ending with `Z` |
| `source` | Constant `odoo` |
| `odoo_company_id` | Positive integer |
| `payload` | Event-specific JSON object, no secrets |

Schema: [`envelope.schema.json`](envelope.schema.json)

## Headers

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `User-Agent` | `elmogps-odoo/18.0` |
| `X-ELMOGPS-Event-Id` | Same as `event_id` |
| `X-ELMOGPS-Event-Type` | Same as `event_type` |
| `X-ELMOGPS-Event-Version` | Same as `event_version` |
| `X-ELMOGPS-Timestamp` | Unix timestamp (seconds) |
| `X-ELMOGPS-Signature` | `sha256=<lowercase_hex>` |

## HMAC signing

- Algorithm: **HMAC-SHA256**
- String to sign: `{timestamp}.{raw_body}`
- `raw_body` is the exact UTF-8 bytes sent on the wire
- Signature header: `sha256=<hexdigest>`
- Test secret (tests only): `test-secret-not-for-production`
- Test vector: [`test-vectors/hmac-sha256.json`](test-vectors/hmac-sha256.json)

## JSON serialization

Odoo serializes outbound bodies with:

```python
json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
```

No pretty-print. HMAC is computed on the final serialized string. Payload hash stored in outbox is SHA-256 of the same canonical body.

## Replay protection

- Backend replay window: **300 seconds**
- Odoo generates a new timestamp per delivery attempt
- `event_id` and payload body remain unchanged on retry
- Signature is recomputed per attempt because timestamp changes

## Idempotency

- Key: `source + event_id` → effectively `odoo:{event_id}`
- One outbox row per business operation
- Retries reuse the same `event_id` and stored payload
- `payload_hash` is SHA-256 of canonical envelope JSON

## Retry policy

| Attempt | Delay after failure |
|--------:|---------------------|
| 1 | immediately |
| 2 | 1 minute |
| 3 | 5 minutes |
| 4 | 15 minutes |
| 5 | 1 hour |
| 6 | 6 hours |
| 7 | 24 hours |
| 8 | 48 hours |

After max attempts: `status = dead`. Manual retry resets to `pending` without changing `event_id` or payload.

### HTTP classification

| Status | Retryable |
|--------|-----------|
| 200, 202 | Success (sent) |
| 400, 401, 403, 409, 413, 422 | Non-retryable → dead |
| 429, 5xx, timeout | Retryable |
| Integration disabled | No HTTP call |

## Response contract

Success:

```json
{
  "status": "accepted",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "duplicate": false,
  "received_at": "2026-06-17T12:00:01Z"
}
```

Duplicate:

```json
{
  "status": "already_processed",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "duplicate": true,
  "received_at": "2026-06-17T12:00:01Z"
}
```

Error:

```json
{
  "error": {
    "code": "unsupported_event_version",
    "message": "Event version is not supported"
  },
  "event_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Odoo decisions use HTTP status and `error.code`, not human messages.

## Supported events (v1)

| Event | Schema | Odoo implementation |
|-------|--------|---------------------|
| `customer.activated` | [schema](events/customer.activated.schema.json) | Implemented |
| `customer.updated` | [schema](events/customer.updated.schema.json) | Implemented |
| `customer.suspended` | [schema](events/customer.suspended.schema.json) | Implemented |
| `subscription.activated` | [schema](events/subscription.activated.schema.json) | Implemented |
| `subscription.renewed` | [schema](events/subscription.renewed.schema.json) | Implemented |
| `subscription.changed` | [schema](events/subscription.changed.schema.json) | Implemented (contract suspend) |
| `subscription.expired` | [schema](events/subscription.expired.schema.json) | Implemented |
| `subscription.cancelled` | [schema](events/subscription.cancelled.schema.json) | Implemented |
| `device.allocated` | [schema](events/device.allocated.schema.json) | Implemented |
| `device.released` | [schema](events/device.released.schema.json) | Implemented |
| `sim.allocated` | [schema](events/sim.allocated.schema.json) | Implemented |
| `sim.released` | [schema](events/sim.released.schema.json) | Implemented |
| `installation.completed` | [schema](events/installation.completed.schema.json) | Implemented |
| `installation.removed` | [schema](events/installation.removed.schema.json) | Implemented |
| `maintenance.opened` | [schema](events/maintenance.opened.schema.json) | Implemented |
| `maintenance.closed` | [schema](events/maintenance.closed.schema.json) | Implemented |

## Source of truth matrix

| Data | Source | Sent to ELMOGPS in v1 |
|------|--------|------------------------|
| Commercial customer | Odoo | Limited operational reference |
| Contract / subscription | Odoo | Status, limits, dates |
| Invoices / payments | Odoo | **Not sent** |
| GPS device / IMEI | Odoo | Reference + IMEI string |
| SIM / ICCID | Odoo | Reference + ICCID string |
| Installation | Odoo | Completion / removal events |
| Operational tenant | ELMOGPS | UUID when known |
| Live location / trips | Traccar/ELMOGPS | **Not sent to Odoo in v1** |

## Out of scope for v1

- Invoice/payment sync
- Location/trip/alert sync
- Reverse webhooks (ELMOGPS → Odoo)
- Production webhook activation
- Attachments/binary payloads
- User password or token export

## Versioning

Compatible: optional fields, new event types, new enum values when consumers ignore unknowns.  
Breaking: remove/rename fields, change types/meanings, change signing format → requires `event_version = 2`.

## Limits

- Max body size: **256 KiB**
- Connection timeout: **5 s**
- Read timeout: **10 s**
- No binary attachments in payload
