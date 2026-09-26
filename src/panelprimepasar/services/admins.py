from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.models import StaffAdmin
from panelprimepasar.security import AdminRole, Permission, has_permission


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
