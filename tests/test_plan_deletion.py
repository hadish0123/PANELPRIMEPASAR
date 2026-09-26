from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from panelprimepasar import admin_panel
from panelprimepasar.security import AdminRole


class FakePlanSession:
    def __init__(self, plan: SimpleNamespace, references: list[UUID | None]) -> None:
        self.plan = plan
        self.references = references
        self.deleted: object | None = None
        self.committed = False
        self.rolled_back = False

    async def get(self, model: object, plan_id: UUID) -> object:
        return self.plan

    async def scalar(self, statement: object) -> UUID | None:
        return self.references.pop(0)

    async def delete(self, plan: object) -> None:
        self.deleted = plan

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
async def test_plan_with_order_history_cannot_be_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = SimpleNamespace(id=uuid4(), name="پلن استفاده‌شده")
    session = FakePlanSession(plan, [uuid4(), None])
    monkeypatch.setattr(admin_panel, "_require_web_permission", _owner_principal)

    with pytest.raises(HTTPException) as raised:
        await admin_panel.delete_plan(plan.id, session)

    assert raised.value.status_code == 409
    assert "غیرفعال" in str(raised.value.detail)
    assert session.deleted is None
    assert session.committed is False


@pytest.mark.asyncio
async def test_unused_plan_is_permanently_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = SimpleNamespace(id=uuid4(), name="پلن بدون استفاده")
    session = FakePlanSession(plan, [None, None])
    audit: dict[str, object] = {}

    async def record_event(session_arg: object, **kwargs: object) -> None:
        audit.update(kwargs)

    monkeypatch.setattr(admin_panel, "_require_web_permission", _owner_principal)
    monkeypatch.setattr(admin_panel, "record_audit_event", record_event)

    result = await admin_panel.delete_plan(plan.id, session)

    assert result == {"id": str(plan.id), "deleted": True}
    assert session.deleted is plan
    assert session.committed is True
    assert audit["action"] == "plan.deleted"
    assert audit["entity_id"] == str(plan.id)
