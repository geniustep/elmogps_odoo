"""ELMOGPS Odoo Integration Contract v1 — shared constants and helpers."""

import hashlib
import hmac
import json
import re

CONTRACT_VERSION = 1
CONTRACT_NAME = "ELMOGPS Odoo Integration Contract — v1"

USER_AGENT = "elmogps-odoo/18.0"
WEBHOOK_PATH = "/api/v1/integrations/odoo/events"
EVENT_SOURCE = "odoo"

CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 10
MAX_BODY_BYTES = 256 * 1024
REPLAY_WINDOW_SECONDS = 300

TEST_SECRET = "test-secret-not-for-production"

# Contract v1 retry schedule (seconds after failure, before next attempt).
RETRY_DELAYS_SECONDS = [0, 60, 300, 900, 3600, 21600, 86400, 172800]
MAX_ATTEMPTS_DEFAULT = len(RETRY_DELAYS_SECONDS)

NON_RETRYABLE_HTTP_STATUSES = frozenset({400, 401, 403, 409, 413, 422})
RETRYABLE_HTTP_STATUSES = frozenset(range(500, 600)) | frozenset({429})

SUPPORTED_EVENT_TYPES = frozenset(
    {
        "customer.activated",
        "customer.updated",
        "customer.suspended",
        "subscription.activated",
        "subscription.renewed",
        "subscription.changed",
        "subscription.expired",
        "subscription.cancelled",
        "device.allocated",
        "device.released",
        "sim.allocated",
        "sim.released",
        "installation.completed",
        "installation.removed",
        "maintenance.opened",
        "maintenance.closed",
    }
)

SECRET_KEY_PATTERN = re.compile(
    r"(password|secret|token|authorization|pin|puk)", re.IGNORECASE
)

SUBSCRIPTION_OPERATIONAL_STATUSES = frozenset(
    {"trial", "active", "suspended", "expired", "cancelled"}
)

CONTRACT_TO_SUBSCRIPTION_STATUS = {
    "draft": "trial",
    "confirmed": "trial",
    "active": "active",
    "suspended": "suspended",
    "expired": "expired",
    "cancelled": "cancelled",
}

SUSPENSION_REASON_CODES = frozenset(
    {
        "payment_overdue",
        "contract_expired",
        "manual",
        "fraud_review",
        "customer_request",
        "other",
    }
)


def canonical_json_dumps(data):
    """Serialize JSON for signing and storage (contract v1)."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def payload_hash(raw_body):
    return hashlib.sha256(raw_body.encode("utf-8")).hexdigest()


def sign_body(timestamp, raw_body, secret):
    message = f"{timestamp}.{raw_body}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_signature_headers(event_id, event_type, event_version, raw_body, timestamp, secret):
    signature = sign_body(timestamp, raw_body, secret)
    return {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-ELMOGPS-Event-Id": event_id,
        "X-ELMOGPS-Event-Type": event_type,
        "X-ELMOGPS-Event-Version": str(event_version),
        "X-ELMOGPS-Timestamp": timestamp,
        "X-ELMOGPS-Signature": signature,
    }


def validate_headers_match_body(headers, envelope):
    """Ensure header values match envelope fields."""
    errors = []
    if headers.get("X-ELMOGPS-Event-Id") != envelope.get("event_id"):
        errors.append("event_id mismatch")
    if headers.get("X-ELMOGPS-Event-Type") != envelope.get("event_type"):
        errors.append("event_type mismatch")
    if str(headers.get("X-ELMOGPS-Event-Version")) != str(envelope.get("event_version")):
        errors.append("event_version mismatch")
    return errors


def classify_delivery_result(success, status_code):
    """Return (is_success, is_retryable)."""
    if success and status_code in (200, 202):
        return True, False
    if not success or status_code == 0:
        return False, True
    if status_code in NON_RETRYABLE_HTTP_STATUSES:
        return False, False
    if status_code in RETRYABLE_HTTP_STATUSES:
        return False, True
    if 200 <= status_code < 300:
        return True, False
    return False, True


def next_retry_delay_seconds(attempts):
    """attempts is 1-based count after a failed delivery."""
    index = min(attempts, len(RETRY_DELAYS_SECONDS) - 1)
    return RETRY_DELAYS_SECONDS[index]


def contains_forbidden_secrets(payload_obj):
    """Walk JSON structure and reject obvious secret keys."""

    def _walk(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if SECRET_KEY_PATTERN.search(str(key)):
                    return True
                if _walk(value, f"{path}.{key}"):
                    return True
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                if _walk(item, f"{path}[{idx}]"):
                    return True
        return False

    return _walk(payload_obj)


def validate_envelope(envelope):
    errors = []
    required = (
        "event_id",
        "event_type",
        "event_version",
        "occurred_at",
        "source",
        "odoo_company_id",
        "payload",
    )
    for field in required:
        if field not in envelope:
            errors.append(f"missing:{field}")
    if envelope.get("source") != EVENT_SOURCE:
        errors.append("invalid:source")
    if envelope.get("event_type") not in SUPPORTED_EVENT_TYPES:
        errors.append("invalid:event_type")
    if envelope.get("event_version") != CONTRACT_VERSION:
        errors.append("invalid:event_version")
    if not isinstance(envelope.get("payload"), dict):
        errors.append("invalid:payload")
    elif contains_forbidden_secrets(envelope["payload"]):
        errors.append("forbidden:secrets_in_payload")
    return errors


def date_to_iso_datetime(value):
    if not value:
        return None
    return f"{value.isoformat()}T00:00:00Z"
