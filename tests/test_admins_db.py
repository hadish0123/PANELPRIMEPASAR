from uuid import uuid4

import pytest

from panelprimepasar.db import SessionFactory
from panelprimepasar.security import AdminRole, Permission
from panelprimepasar.services.admins import (
    admin_has_permission,
    set_staff_admin_active,
    upsert_staff_admin,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_staff_admin_permissions_and_disable() -> None:
    telegram_id = int(uuid4().hex[:14], 16)

    async with SessionFactory() as session:
        staff = await upsert_staff_admin(
            session,
            telegram_user_id=telegram_id,
            role=AdminRole.SALES,
        )

        assert await admin_has_permission(
            session,
            telegram_user_id=telegram_id,
            permission=Permission.VIEW_ORDERS,
        )
        assert not await admin_has_permission(
            session,
            telegram_user_id=telegram_id,
            permission=Permission.APPROVE_PAYMENTS,
        )

        await set_staff_admin_active(
            session,
            staff_id=staff.id,
            is_active=False,
        )
        assert not await admin_has_permission(
            session,
            telegram_user_id=telegram_id,
            permission=Permission.VIEW_ORDERS,
        )
        await session.rollback()
