from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.integrations.pasarguard import PasarGuardAdmin, PasarGuardError
from panelprimepasar.models import (
    Customer,
    Order,
    OrderKind,
    OrderStatus,
    PasarGuardAccount,
    Plan,
    Subscription,
    SubscriptionStatus,
)


class SubscriptionStateError(RuntimeError):
    """Raised when a subscription operation is invalid."""


class SubscriptionClient(Protocol):
    async def modify_admin_by_id(
        self,
        admin_id: int,
        *,
        password: str | None = None,
        role_id: int | None = None,
        data_limit: int | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> PasarGuardAdmin: ...


@dataclass(frozen=True, slots=True)
class SubscriptionActionOutcome:
    success: bool
    subscription_id: UUID
    error_code: str | None = None
    error_message: str | None = None


async def list_customer_subscriptions(
    session: AsyncSession,
    *,
    customer_id: UUID,
) -> list[Subscription]:
    rows = await session.scalars(
        select(Subscription)
        .where(Subscription.customer_id == customer_id)
        .order_by(Subscription.created_at.desc())
    )
    return list(rows.all())


async def get_customer_subscription(
    session: AsyncSession,
    *,
    customer_id: UUID,
    subscription_id: UUID,
) -> Subscription | None:
    return await session.scalar(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.customer_id == customer_id,
        )
    )


async def create_lifecycle_order(
    session: AsyncSession,
    *,
    customer: Customer,
    subscription: Subscription,
    plan: Plan,
    kind: OrderKind,
    idempotency_key: str,
) -> tuple[Order, bool]:
    if kind not in {OrderKind.RENEWAL, OrderKind.TOPUP}:
        raise SubscriptionStateError("Lifecycle order kind must be renewal or topup")

    existing = await session.scalar(
        select(Order).where(Order.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, False

    order = Order(
        customer_id=customer.id,
        plan_id=plan.id,
        kind=kind,
        target_subscription_id=subscription.id,
        status=OrderStatus.AWAITING_PAYMENT,
        price_amount=plan.price_amount,
        currency=plan.currency,
        quota_bytes=plan.quota_bytes,
        validity_days=plan.validity_days,
        idempotency_key=idempotency_key,
    )
    try:
        async with session.begin_nested():
            session.add(order)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(Order).where(Order.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing, False

    return order, True


async def apply_paid_lifecycle_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    client: SubscriptionClient,
) -> SubscriptionActionOutcome:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None:
        raise SubscriptionStateError("Order not found")
    if order.kind not in {OrderKind.RENEWAL, OrderKind.TOPUP}:
        raise SubscriptionStateError("Order is not a lifecycle order")
    if order.target_subscription_id is None:
        raise SubscriptionStateError("Lifecycle order has no target subscription")
    if order.status == OrderStatus.COMPLETED:
        return SubscriptionActionOutcome(
            success=True,
            subscription_id=order.target_subscription_id,
        )
    if order.status not in {OrderStatus.PAID, OrderStatus.PROVISIONING, OrderStatus.FAILED}:
        raise SubscriptionStateError(
            f"Order status {order.status.value!r} cannot be applied"
        )

    subscription = await session.scalar(
        select(Subscription)
        .where(Subscription.id == order.target_subscription_id)
        .with_for_update()
    )
    if subscription is None:
        raise SubscriptionStateError("Subscription not found")

    account = await session.scalar(
        select(PasarGuardAccount)
        .where(PasarGuardAccount.id == subscription.pasar_guard_account_id)
        .with_for_update()
    )
    if account is None or account.pasarguard_admin_id is None:
        raise SubscriptionStateError("PasarGuard account is not provisioned")

    order.status = OrderStatus.PROVISIONING
    await session.flush()

    try:
        if order.kind == OrderKind.TOPUP:
            new_quota = account.quota_bytes + order.quota_bytes
            await client.modify_admin_by_id(
                account.pasarguard_admin_id,
                data_limit=new_quota,
                status="active",
                note=f"PANELPRIMEPASAR topup order {order.id}",
            )
            account.quota_bytes = new_quota
            subscription.quota_bytes = new_quota
        else:
            await client.modify_admin_by_id(
                account.pasarguard_admin_id,
                status="active",
                note=f"PANELPRIMEPASAR renewal order {order.id}",
            )
            now = datetime.now(UTC)
            if order.validity_days is None:
                subscription.expires_at = None
            else:
                base = now
                if subscription.expires_at is not None and subscription.expires_at > now:
                    base = subscription.expires_at
                subscription.expires_at = base + timedelta(days=order.validity_days)
            subscription.plan_id = order.plan_id

        account.is_active = True
        subscription.status = SubscriptionStatus.ACTIVE.value
        order.status = OrderStatus.COMPLETED
        await session.flush()
    except PasarGuardError as exc:
        order.status = OrderStatus.FAILED
        await session.flush()
        return SubscriptionActionOutcome(
            success=False,
            subscription_id=subscription.id,
            error_code=type(exc).__name__,
            error_message=str(exc)[:1000],
        )

    return SubscriptionActionOutcome(
        success=True,
        subscription_id=subscription.id,
    )
