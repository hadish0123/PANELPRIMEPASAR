from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
)


class PaymentStateError(RuntimeError):
    """Raised when a payment transition would violate order/payment state."""


async def _locked_payment(session: AsyncSession, payment_id: UUID) -> tuple[Order, Payment]:
    # Every payment transition locks the order first, then its payment(s).
    order_id = await session.scalar(select(Payment.order_id).where(Payment.id == payment_id))
    if order_id is None:
        raise PaymentStateError("Payment not found")
    order = await session.scalar(
        select(Order)
        .where(Order.id == order_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    payment = await session.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if order is None or payment is None:
        raise PaymentStateError("Payment order not found")
    return order, payment


async def create_pending_payment(
    session: AsyncSession,
    *,
    order_id: UUID,
    provider: str,
    raw_reference: str | None = None,
) -> Payment:
    order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise PaymentStateError("Order not found")

    if await session.scalar(select(Customer.is_blocked).where(Customer.id == order.customer_id)):
        raise PaymentStateError("Customer is blocked")

    if order.status not in {
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.PENDING,
    }:
        raise PaymentStateError(f"Order status {order.status.value!r} cannot start a payment")

    existing = await session.scalar(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.provider == provider,
            Payment.status == PaymentStatus.PENDING,
        )
        .order_by(Payment.created_at.desc())
    )
    if existing is not None:
        if raw_reference is not None:
            existing.raw_reference = raw_reference
            await session.flush()
        return existing

    payment = Payment(
        order_id=order.id,
        provider=provider,
        amount=order.price_amount,
        currency=order.currency,
        status=PaymentStatus.PENDING,
        raw_reference=raw_reference,
    )
    session.add(payment)
    order.status = OrderStatus.AWAITING_PAYMENT
    await session.flush()
    return payment


async def verify_payment(
    session: AsyncSession,
    *,
    payment_id: UUID,
    provider_transaction_id: str,
    verified_amount: int,
    verified_currency: str,
) -> Payment:
    order, payment = await _locked_payment(session, payment_id)

    if not provider_transaction_id.strip() or len(provider_transaction_id) > 191:
        raise PaymentStateError("Invalid provider transaction ID")

    if verified_amount != payment.amount or verified_amount != order.price_amount:
        raise PaymentStateError("Verified payment amount does not match the order")

    expected_currency = payment.currency.upper()
    if (
        verified_currency.upper() != expected_currency
        or order.currency.upper() != expected_currency
    ):
        raise PaymentStateError("Verified payment currency does not match the order")

    if payment.status == PaymentStatus.VERIFIED:
        if payment.provider_transaction_id != provider_transaction_id:
            raise PaymentStateError("Verified payment cannot be reassigned to another transaction")
        return payment

    if payment.status != PaymentStatus.PENDING:
        raise PaymentStateError(f"Payment status {payment.status.value!r} cannot be verified")

    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        raise PaymentStateError(f"Order status {order.status.value!r} cannot accept a payment")

    duplicate = await session.scalar(
        select(Payment.id).where(Payment.provider_transaction_id == provider_transaction_id)
    )
    if duplicate is not None and duplicate != payment.id:
        raise PaymentStateError("Transaction already belongs to another payment")

    payment.provider_transaction_id = provider_transaction_id
    payment.status = PaymentStatus.VERIFIED
    payment.verified_at = datetime.now(UTC)
    order.status = OrderStatus.PAID
    other_pending = await session.scalars(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.id != payment.id,
            Payment.status == PaymentStatus.PENDING,
        )
        .with_for_update()
    )
    for other in other_pending:
        other.status = PaymentStatus.FAILED
    await session.flush()
    return payment


async def fail_payment(
    session: AsyncSession,
    *,
    payment_id: UUID,
) -> Payment:
    _, payment = await _locked_payment(session, payment_id)

    if payment.status not in {PaymentStatus.PENDING, PaymentStatus.FAILED}:
        raise PaymentStateError("Only a pending payment can be marked failed")

    payment.status = PaymentStatus.FAILED
    await session.flush()
    return payment


async def approve_manual_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    actor_telegram_id: int,
) -> Payment:
    order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise PaymentStateError("Order not found")

    if order.status in {
        OrderStatus.PAID,
        OrderStatus.PROVISIONING,
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
    }:
        verified = await session.scalar(
            select(Payment)
            .where(
                Payment.order_id == order.id,
                Payment.status == PaymentStatus.VERIFIED,
            )
            .order_by(Payment.verified_at.desc())
        )
        if verified is not None:
            return verified
        raise PaymentStateError("Order is past payment stage but no verified payment record exists")

    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise PaymentStateError(f"Order status {order.status.value!r} cannot be manually approved")

    payment = await session.scalar(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.provider == "manual",
            Payment.status == PaymentStatus.PENDING,
        )
        .order_by(Payment.created_at.desc())
    )
    if payment is None:
        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
            raw_reference=f"approved-by-telegram:{actor_telegram_id}",
        )
    return await verify_payment(
        session,
        payment_id=payment.id,
        provider_transaction_id=f"manual:{payment.id}",
        verified_amount=order.price_amount,
        verified_currency=order.currency,
    )
