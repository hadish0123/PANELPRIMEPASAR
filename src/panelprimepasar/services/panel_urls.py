from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings
from panelprimepasar.models import (
    PasarGuardAccount,
    PasarGuardInstance,
)


async def resolve_order_panel_url(
    session: AsyncSession,
    *,
    settings: Settings,
    order_id: UUID,
) -> str:
    account = await session.scalar(
        select(PasarGuardAccount).where(
            PasarGuardAccount.order_id == order_id
        )
    )
    if account is not None and account.pasarguard_instance_id is not None:
        instance = await session.get(
            PasarGuardInstance,
            account.pasarguard_instance_id,
        )
        if instance is not None:
            return instance.base_url.rstrip("/")

    return str(settings.pasarguard_base_url).rstrip("/")
