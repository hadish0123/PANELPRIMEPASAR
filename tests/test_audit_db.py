import json

import pytest

from panelprimepasar.db import SessionFactory
from panelprimepasar.services.audit import record_audit_event


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_event_serializes_non_secret_metadata() -> None:
    async with SessionFactory() as session:
        event = await record_audit_event(
            session,
            actor_type="telegram_owner",
            actor_id="12345",
            action="payment.manual_approved",
            entity_type="order",
            entity_id="order-id",
            correlation_id="order-id",
            metadata={"provider": "manual", "amount": 200_000, "currency": "IRT"},
        )

        assert event.metadata_json is not None
        payload = json.loads(event.metadata_json)
        assert payload["provider"] == "manual"
        assert "password" not in payload
        await session.rollback()
