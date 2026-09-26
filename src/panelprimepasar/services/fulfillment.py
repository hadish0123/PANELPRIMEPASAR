from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings
from panelprimepasar.integrations.pasarguard import PasarGuardError
from panelprimepasar.models import (
    Order,
    OrderKind,
    PasarGuardAccount,
    Subscription,
)
from panelprimepasar.services.pasarguard_instances import PasarGuardInstanceRouter
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
    order = await session.scalar(select(Order).where(Order.id == order_id))
    if order is None:
        raise ProvisioningStateError("Order not found")

    instance_router = PasarGuardInstanceRouter(settings=settings)

    if order.kind == OrderKind.NEW:
        account = await session.scalar(
            select(PasarGuardAccount).where(
                PasarGuardAccount.order_id == order.id
            )
        )
        target = (
            await instance_router.target_for_account(
                session,
                account=account,
            )
            if account is not None
            else await instance_router.select_for_new_order(
                session,
                routing_key=str(order.id),
            )
        )
    else:
        if order.target_subscription_id is None:
            raise SubscriptionStateError(
                "Lifecycle order has no target subscription"
            )
        subscription = await session.get(
            Subscription,
            order.target_subscription_id,
        )
        if subscription is None:
            raise SubscriptionStateError("Subscription not found")
        account = await session.get(
            PasarGuardAccount,
            subscription.pasar_guard_account_id,
        )
        if account is None:
            raise SubscriptionStateError("PasarGuard account not found")
        target = await instance_router.target_for_account(
            session,
            account=account,
        )

    try:
        if order.kind == OrderKind.NEW:
            service = ProvisioningService(
                client=target.client,
                reseller_role_id=target.reseller_role_id,
                reseller_role_name=target.reseller_role_name,
                pasarguard_instance_id=target.instance_id,
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
            client=target.client,
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
        await target.client.close()
