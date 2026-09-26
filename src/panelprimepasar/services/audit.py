import json
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import AuditEvent

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "merchant_id",
    "bearer",
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _sanitize_audit_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            sanitized[key] = (
                _REDACTED
                if _is_sensitive_key(key)
                else _sanitize_audit_value(raw_value)
            )
        return sanitized

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_sanitize_audit_value(item) for item in value]

    return value


def sanitize_audit_metadata(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if metadata is None:
        return None
    sanitized = _sanitize_audit_value(metadata)
    if not isinstance(sanitized, dict):
        return None
    return sanitized


async def record_audit_event(
    session: AsyncSession,
    *,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    correlation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    safe_metadata = sanitize_audit_metadata(metadata)
    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        metadata_json=(
            json.dumps(safe_metadata, ensure_ascii=False, sort_keys=True)
            if safe_metadata is not None
            else None
        ),
    )
    session.add(event)
    await session.flush()
    return event
