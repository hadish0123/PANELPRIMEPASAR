from uuid import uuid4

import pytest

from panelprimepasar.db import SessionFactory
from panelprimepasar.security import AdminRole, Permission
from panelprimepasar.services.admins import (
    admin_has_permission,
    authenticate_web_staff,
    set_staff_admin_active,
    set_web_staff_password,
    upsert_staff_admin,
    upsert_web_staff_admin,
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



@pytest.mark.asyncio(loop_scope="session")
async def test_web_staff_credentials_and_password_rotation() -> None:
    marker = uuid4().hex
    username = f"finance_{marker[:8]}"
    original_password = "original-password-123!"
    rotated_password = "rotated-password-456!"

    async with SessionFactory() as session:
        staff = await upsert_web_staff_admin(
            session,
            username=username,
            password=original_password,
            role=AdminRole.FINANCE,
        )

        authenticated = await authenticate_web_staff(
            session,
            username=username.upper(),
            password=original_password,
        )
        assert authenticated is not None
        assert authenticated.id == staff.id
        assert authenticated.role == AdminRole.FINANCE.value

        assert (
            await authenticate_web_staff(
                session,
                username=username,
                password="incorrect-password-999!",
            )
            is None
        )

        await set_web_staff_password(
            session,
            staff_id=staff.id,
            password=rotated_password,
        )
        assert (
            await authenticate_web_staff(
                session,
                username=username,
                password=original_password,
            )
            is None
        )
        rotated = await authenticate_web_staff(
            session,
            username=username,
            password=rotated_password,
        )
        assert rotated is not None
        assert rotated.id == staff.id
        await session.rollback()
