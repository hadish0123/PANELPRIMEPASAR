from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings
from panelprimepasar.integrations.factory import build_pasarguard_client
from panelprimepasar.integrations.pasarguard import PasarGuardError
from panelprimepasar.models import Order, OrderKind
from panelprimepasar.services.provisioning import (
    ProvisionedCredentials,
    ProvisioningService,
    ProvisioningStateError,
)
from panelprimepasar.services.subscriptions import (
    SubscriptionStateError,
    apply_paid_lifecycle_order,
)


@dataclass(frozen=True, slots=True)
class FulfillmentOutcome:
    success: bool
    order_kind: OrderKind
    credentials: ProvisionedCredentials | None = None
    already_provisioned: bool = False
    error_code: str | None = None
    error_message: str | None = None


async def fulfill_paid_order(
    session: AsyncSession,
    *,
    settings: Settings,
    order_id: UUID,
) -> FulfillmentOutcome:
    order = await session.scalar(
        select(Order).where(Order.id == order_id)
    )
    if order is None:
        raise ProvisioningStateError("Order not found")

    client = build_pasarguard_client(settings)
    try:
        if order.kind == OrderKind.NEW:
            service = ProvisioningService(
                client=client,
                reseller_role_id=settings.pasarguard_reseller_role_id,
                reseller_role_name=settings.pasarguard_reseller_role_name,
            )
            result = await service.provision_paid_order(
                session,
                order_id=order.id,
            )
            return FulfillmentOutcome(
                success=result.success,
                order_kind=order.kind,
                credentials=result.credentials,
                already_provisioned=result.already_provisioned,
                error_code=result.error_code,
                error_message=result.error_message,
            )

        lifecycle = await apply_paid_lifecycle_order(
            session,
            order_id=order.id,
            client=client,
        )
        return FulfillmentOutcome(
            success=lifecycle.success,
            order_kind=order.kind,
            error_code=lifecycle.error_code,
            error_message=lifecycle.error_message,
        )
    except (PasarGuardError, SubscriptionStateError, ProvisioningStateError):
        raise
    finally:
        await client.close()
