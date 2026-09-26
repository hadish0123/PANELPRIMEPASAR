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



@pytest.mark.asyncio(loop_scope="session")
async def test_audit_event_redacts_nested_secrets() -> None:
    async with SessionFactory() as session:
        event = await record_audit_event(
            session,
            actor_type="system",
            actor_id=None,
            action="security.redaction_test",
            entity_type="test",
            entity_id="1",
            metadata={
                "username": "visible-user",
                "password": "must-not-leak",
                "nested": {
                    "api_key": "secret-api-key",
                    "merchant_id": "merchant-secret",
                    "safe": "visible",
                },
                "items": [
                    {"token": "secret-token"},
                    {"value": 123},
                ],
            },
        )

        assert event.metadata_json is not None
        payload = json.loads(event.metadata_json)
        assert payload["username"] == "visible-user"
        assert payload["password"] == "[REDACTED]"
        assert payload["nested"]["api_key"] == "[REDACTED]"
        assert payload["nested"]["merchant_id"] == "[REDACTED]"
        assert payload["nested"]["safe"] == "visible"
        assert payload["items"][0]["token"] == "[REDACTED]"
        assert payload["items"][1]["value"] == 123
        assert "must-not-leak" not in event.metadata_json
        assert "secret-api-key" not in event.metadata_json
        assert "secret-token" not in event.metadata_json
        await session.rollback()
