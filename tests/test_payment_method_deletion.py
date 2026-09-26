from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from panelprimepasar import admin_panel
from panelprimepasar.security import AdminRole


class FakePaymentMethodSession:
    def __init__(self, method: SimpleNamespace, payment_reference: UUID | None) -> None:
        self.method = method
        self.payment_reference = payment_reference
        self.deleted: object | None = None
        self.committed = False
        self.rolled_back = False

    async def get(self, model: object, method_id: UUID) -> object:
        return self.method

    async def scalar(self, statement: object) -> UUID | None:
        return self.payment_reference

    async def delete(self, method: object) -> None:
        self.deleted = method

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


async def _owner_principal(*args: object, **kwargs: object) -> admin_panel.WebAdminPrincipal:
    return admin_panel.WebAdminPrincipal(
        role=AdminRole.OWNER,
        staff_id=None,
        username="owner",
    )


@pytest.mark.asyncio
async def test_payment_method_with_history_cannot_be_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    method = SimpleNamespace(
        id=uuid4(),
        slug="used-card",
        kind="manual_card",
    )
    session = FakePaymentMethodSession(method, uuid4())
    monkeypatch.setattr(admin_panel, "_require_web_permission", _owner_principal)

    with pytest.raises(HTTPException) as raised:
        await admin_panel.delete_payment_method(method.id, session)

    assert raised.value.status_code == 409
    assert "غیرفعال" in str(raised.value.detail)
    assert session.deleted is None
    assert session.committed is False


@pytest.mark.asyncio
async def test_unused_payment_method_is_permanently_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    method = SimpleNamespace(
        id=uuid4(),
        slug="unused-card",
        kind="manual_card",
    )
    session = FakePaymentMethodSession(method, None)
    audit: dict[str, object] = {}

    async def record_event(session_arg: object, **kwargs: object) -> None:
        audit.update(kwargs)

    monkeypatch.setattr(admin_panel, "_require_web_permission", _owner_principal)
    monkeypatch.setattr(admin_panel, "record_audit_event", record_event)

    result = await admin_panel.delete_payment_method(method.id, session)

    assert result == {"id": str(method.id), "deleted": True}
    assert session.deleted is method
    assert session.committed is True
    assert audit["action"] == "payment_method.deleted"
    assert audit["entity_id"] == str(method.id)
