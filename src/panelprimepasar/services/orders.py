from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import Customer, Order, OrderStatus, Plan


class OrderStateError(RuntimeError):
    """Checkout or cancellation would violate the order state."""


async def upsert_customer(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> Customer:
    values = dict(
        telegram_username=telegram_username,
        first_name=first_name,
        last_name=last_name,
    )
    statement = insert(Customer).values(telegram_user_id=telegram_user_id, **values)
    customer = await session.scalar(
        statement.on_conflict_do_update(
            index_elements=[Customer.telegram_user_id],
            set_=values,
        ).returning(Customer),
        execution_options={"populate_existing": True},
    )
    assert customer is not None
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
    locked_customer = await session.scalar(
        select(Customer)
        .where(Customer.id == customer.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if locked_customer is None or locked_customer.is_blocked:
        raise OrderStateError("Customer is blocked")
    locked_plan = await session.scalar(
        select(Plan)
        .where(Plan.id == plan.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if locked_plan is None or not locked_plan.is_active:
        raise OrderStateError("Plan is no longer active")
    existing = await session.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.customer_id != customer.id or existing.plan_id != plan.id:
            raise OrderStateError("Checkout key belongs to another purchase")
        return existing, False

    order = Order(
        customer_id=customer.id,
        plan_id=plan.id,
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


async def cancel_order(session: AsyncSession, *, order_id: UUID) -> Order:
    from panelprimepasar.models import Payment, PaymentStatus

    order = await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None:
        raise OrderStateError("Order not found")
    if order.status == OrderStatus.CANCELED:
        return order
    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        raise OrderStateError("Only unpaid orders can be canceled")
    payments = list(
        (
            await session.scalars(
                select(Payment).where(Payment.order_id == order.id).with_for_update()
            )
        ).all()
    )
    if any(payment.status == PaymentStatus.VERIFIED for payment in payments):
        raise OrderStateError("A paid order cannot be canceled")
    for payment in payments:
        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
    order.status = OrderStatus.CANCELED
    await session.flush()
    return order


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
