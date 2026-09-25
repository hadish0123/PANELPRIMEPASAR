import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import AuditEvent


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
    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        metadata_json=(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            if metadata is not None
            else None
        ),
    )
    session.add(event)
    await session.flush()
    return event
