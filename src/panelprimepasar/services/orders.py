from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import Customer, Order, OrderStatus, Plan


async def upsert_customer(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> Customer:
    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == telegram_user_id)
    )

    if customer is None:
        customer = Customer(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(customer)
    else:
        customer.telegram_username = telegram_username
        customer.first_name = first_name
        customer.last_name = last_name

    await session.flush()
    return customer


async def list_active_plans(session: AsyncSession) -> list[Plan]:
    result = await session.scalars(
        select(Plan)
        .where(Plan.is_active.is_(True))
        .order_by(Plan.sort_order.asc(), Plan.price_amount.asc())
    )
    return list(result.all())


async def get_active_plan(session: AsyncSession, plan_id: UUID) -> Plan | None:
    return await session.scalar(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_active.is_(True),
        )
    )


def checkout_idempotency_key(
    *,
    telegram_user_id: int,
    message_id: int,
    plan_id: UUID,
) -> str:
    return f"telegram:{telegram_user_id}:message:{message_id}:plan:{plan_id}"


async def get_or_create_checkout_order(
    session: AsyncSession,
    *,
    customer: Customer,
    plan: Plan,
    idempotency_key: str,
) -> tuple[Order, bool]:
    existing = await session.scalar(
        select(Order).where(Order.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, False

    order = Order(
        customer_id=customer.id,
        plan_id=plan.id,
        status=OrderStatus.AWAITING_PAYMENT,
        price_amount=plan.price_amount,
        currency=plan.currency,
        quota_bytes=plan.quota_bytes,
        validity_days=None,
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


async def list_customer_orders(
    session: AsyncSession,
    *,
    customer_id: UUID,
    limit: int = 10,
) -> list[Order]:
    result = await session.scalars(
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )
    return list(result.all())
