from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import (
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
)


class PaymentStateError(RuntimeError):
    """Raised when a payment transition would violate order/payment state."""


async def create_pending_payment(
    session: AsyncSession,
    *,
    order_id: UUID,
    provider: str,
    raw_reference: str | None = None,
) -> Payment:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None:
        raise PaymentStateError("Order not found")

    if order.status not in {
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.PENDING,
    }:
        raise PaymentStateError(
            f"Order status {order.status.value!r} cannot start a payment"
        )

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
    payment = await session.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None:
        raise PaymentStateError("Payment not found")

    order = await session.scalar(
        select(Order).where(Order.id == payment.order_id).with_for_update()
    )
    if order is None:
        raise PaymentStateError("Payment order not found")

    if payment.status == PaymentStatus.VERIFIED:
        if payment.provider_transaction_id != provider_transaction_id:
            raise PaymentStateError(
                "Verified payment cannot be reassigned to another transaction"
            )
        return payment

    if payment.status != PaymentStatus.PENDING:
        raise PaymentStateError(
            f"Payment status {payment.status.value!r} cannot be verified"
        )

    if verified_amount != payment.amount or verified_amount != order.price_amount:
        raise PaymentStateError("Verified payment amount does not match the order")

    expected_currency = payment.currency.upper()
    if (
        verified_currency.upper() != expected_currency
        or order.currency.upper() != expected_currency
    ):
        raise PaymentStateError("Verified payment currency does not match the order")

    payment.provider_transaction_id = provider_transaction_id
    payment.status = PaymentStatus.VERIFIED
    payment.verified_at = datetime.now(UTC)
    order.status = OrderStatus.PAID
    await session.flush()
    return payment


async def fail_payment(
    session: AsyncSession,
    *,
    payment_id: UUID,
) -> Payment:
    payment = await session.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if payment is None:
        raise PaymentStateError("Payment not found")

    if payment.status == PaymentStatus.VERIFIED:
        raise PaymentStateError("A verified payment cannot be marked failed")

    payment.status = PaymentStatus.FAILED
    await session.flush()
    return payment
