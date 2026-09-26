from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.models import StaffAdmin
from panelprimepasar.security import (
    AdminRole,
    Permission,
    has_permission,
    hash_password,
    verify_password,
)


class AdminAccessError(RuntimeError):
    """Raised when an admin account or role is invalid."""


async def get_admin_role(
    session: AsyncSession,
    *,
    telegram_user_id: int,
) -> AdminRole | None:
    if telegram_user_id in get_settings().telegram_owner_ids:
        return AdminRole.OWNER

    staff = await session.scalar(
        select(StaffAdmin).where(
            StaffAdmin.telegram_user_id == telegram_user_id,
            StaffAdmin.is_active.is_(True),
        )
    )
    if staff is None:
        return None

    try:
        return AdminRole(staff.role)
    except ValueError:
        return None


async def admin_has_permission(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    permission: Permission,
) -> bool:
    role = await get_admin_role(
        session,
        telegram_user_id=telegram_user_id,
    )
    return role is not None and has_permission(role, permission)


async def upsert_staff_admin(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    role: AdminRole,
    note: str | None = None,
) -> StaffAdmin:
    if role == AdminRole.OWNER:
        raise AdminAccessError(
            "Owner access is configured through TELEGRAM_OWNER_IDS."
        )

    staff = await session.scalar(
        select(StaffAdmin).where(
            StaffAdmin.telegram_user_id == telegram_user_id
        )
    )
    if staff is None:
        staff = StaffAdmin(
            telegram_user_id=telegram_user_id,
            role=role.value,
            is_active=True,
            note=note,
        )
        session.add(staff)
    else:
        staff.role = role.value
        staff.is_active = True
        staff.note = note

    await session.flush()
    return staff


async def set_staff_admin_active(
    session: AsyncSession,
    *,
    staff_id: UUID,
    is_active: bool,
) -> StaffAdmin:
    staff = await session.get(StaffAdmin, staff_id)
    if staff is None:
        raise AdminAccessError("Staff admin not found.")

    staff.is_active = is_active
    await session.flush()
    return staff


async def list_staff_admins(session: AsyncSession) -> list[StaffAdmin]:
    rows = await session.scalars(
        select(StaffAdmin).order_by(
            StaffAdmin.created_at.desc(),
            StaffAdmin.id.desc(),
        )
    )
    return list(rows.all())



async def get_web_staff_admin(
    session: AsyncSession,
    *,
    username: str,
) -> StaffAdmin | None:
    normalized = username.strip().casefold()
    if not normalized:
        return None
    return await session.scalar(
        select(StaffAdmin).where(
            StaffAdmin.login_username == normalized,
            StaffAdmin.is_active.is_(True),
        )
    )


async def authenticate_web_staff(
    session: AsyncSession,
    *,
    username: str,
    password: str,
) -> StaffAdmin | None:
    staff = await get_web_staff_admin(session, username=username)
    if staff is None or not verify_password(password, staff.password_hash):
        return None
    return staff


async def upsert_web_staff_admin(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    role: AdminRole,
    telegram_user_id: int | None = None,
    note: str | None = None,
) -> StaffAdmin:
    if role == AdminRole.OWNER:
        raise AdminAccessError(
            "Owner access is configured through ADMIN_PANEL_API_KEY."
        )

    normalized = username.strip().casefold()
    if len(normalized) < 3 or len(normalized) > 64:
        raise AdminAccessError("Web admin username must be between 3 and 64 characters")
    if not all(ch.isalnum() or ch in {"_", "-", "."} for ch in normalized):
        raise AdminAccessError("Web admin username contains unsupported characters")

    existing_by_username = await session.scalar(
        select(StaffAdmin).where(StaffAdmin.login_username == normalized)
    )
    existing_by_telegram = None
    if telegram_user_id is not None:
        existing_by_telegram = await session.scalar(
            select(StaffAdmin).where(
                StaffAdmin.telegram_user_id == telegram_user_id
            )
        )

    if (
        existing_by_username is not None
        and existing_by_telegram is not None
        and existing_by_username.id != existing_by_telegram.id
    ):
        raise AdminAccessError("Username and Telegram ID belong to different staff records")

    staff = existing_by_username or existing_by_telegram
    if staff is None:
        staff = StaffAdmin(
            telegram_user_id=telegram_user_id,
            login_username=normalized,
            password_hash=hash_password(password),
            role=role.value,
            is_active=True,
            note=note,
        )
        session.add(staff)
    else:
        staff.login_username = normalized
        staff.password_hash = hash_password(password)
        staff.role = role.value
        staff.is_active = True
        staff.note = note
        if telegram_user_id is not None:
            staff.telegram_user_id = telegram_user_id

    await session.flush()
    return staff


async def set_web_staff_password(
    session: AsyncSession,
    *,
    staff_id: UUID,
    password: str,
) -> StaffAdmin:
    staff = await session.get(StaffAdmin, staff_id)
    if staff is None:
        raise AdminAccessError("Staff admin not found.")
    if staff.login_username is None:
        raise AdminAccessError("Staff admin does not have a web username")

    staff.password_hash = hash_password(password)
    await session.flush()
    return staff
