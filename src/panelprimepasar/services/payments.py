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
from panelprimepasar.services.discounts import (
    DiscountStateError,
    redeem_discount_for_order,
    release_discount_for_order,
)


class PaymentStateError(RuntimeError):
    """Raised when a payment transition would violate order/payment state."""


async def create_pending_payment(
    session: AsyncSession,
    *,
    order_id: UUID,
    provider: str,
    raw_reference: str | None = None,
    payment_method_id: UUID | None = None,
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

    existing_query = select(Payment).where(
        Payment.order_id == order.id,
        Payment.provider == provider,
        Payment.status == PaymentStatus.PENDING,
    )
    if payment_method_id is None:
        existing_query = existing_query.where(Payment.payment_method_id.is_(None))
    else:
        existing_query = existing_query.where(
            Payment.payment_method_id == payment_method_id
        )

    existing = await session.scalar(
        existing_query.order_by(Payment.created_at.desc())
    )
    if existing is not None:
        if raw_reference is not None:
            existing.raw_reference = raw_reference
            await session.flush()
        return existing

    payment = Payment(
        order_id=order.id,
        payment_method_id=payment_method_id,
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

    try:
        await redeem_discount_for_order(
            session,
            order_id=order.id,
        )
    except DiscountStateError as exc:
        raise PaymentStateError(str(exc)) from exc

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


async def approve_manual_order(
    session: AsyncSession,
    *,
    order_id: UUID,
    actor_telegram_id: int | None = None,
    actor_reference: str | None = None,
) -> Payment:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
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
        raise PaymentStateError(
            "Order is past payment stage but no verified payment record exists"
        )

    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise PaymentStateError(
            f"Order status {order.status.value!r} cannot be manually approved"
        )

    if actor_reference is None:
        if actor_telegram_id is None:
            raise PaymentStateError("Manual approval actor is required")
        actor_reference = f"telegram:{actor_telegram_id}"

    payment = await session.scalar(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.provider == "manual",
            Payment.status == PaymentStatus.PENDING,
        )
        .order_by(Payment.created_at.desc())
        .with_for_update()
    )
    if payment is None:
        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
            raw_reference=f"approved-by:{actor_reference}",
        )
    else:
        payment.raw_reference = f"approved-by:{actor_reference}"
        await session.flush()

    return await verify_payment(
        session,
        payment_id=payment.id,
        provider_transaction_id=f"manual:{payment.id}",
        verified_amount=order.price_amount,
        verified_currency=order.currency,
    )


async def reject_pending_manual_payment(
    session: AsyncSession,
    *,
    order_id: UUID,
) -> Payment:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None:
        raise PaymentStateError("Order not found")
    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise PaymentStateError(
            f"Order status {order.status.value!r} cannot reject a payment"
        )

    payment = await session.scalar(
        select(Payment)
        .where(
            Payment.order_id == order.id,
            Payment.provider == "manual",
            Payment.status == PaymentStatus.PENDING,
        )
        .order_by(Payment.created_at.desc())
        .with_for_update()
    )
    if payment is None:
        raise PaymentStateError("No pending manual payment was found")

    payment.status = PaymentStatus.FAILED
    order.status = OrderStatus.AWAITING_PAYMENT
    await session.flush()
    return payment


async def cancel_unpaid_order(
    session: AsyncSession,
    *,
    order_id: UUID,
) -> Order:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None:
        raise PaymentStateError("Order not found")

    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise PaymentStateError(
            f"Order status {order.status.value!r} cannot be canceled"
        )

    try:
        await release_discount_for_order(
            session,
            order_id=order.id,
        )
    except DiscountStateError as exc:
        raise PaymentStateError(str(exc)) from exc

    order.status = OrderStatus.CANCELED
    pending_payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(
                    Payment.order_id == order.id,
                    Payment.status == PaymentStatus.PENDING,
                )
                .with_for_update()
            )
        ).all()
    )
    for payment in pending_payments:
        payment.status = PaymentStatus.FAILED

    await session.flush()
    return order



async def settle_zero_price_order(
    session: AsyncSession,
    *,
    order_id: UUID,
) -> Payment:
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None:
        raise PaymentStateError("Order not found")

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

    if order.status not in {
        OrderStatus.PENDING,
        OrderStatus.AWAITING_PAYMENT,
    }:
        raise PaymentStateError(
            f"Order status {order.status.value!r} cannot be settled"
        )
    if order.price_amount != 0:
        raise PaymentStateError("Only zero-price orders can be settled without payment")

    try:
        await redeem_discount_for_order(
            session,
            order_id=order.id,
        )
    except DiscountStateError as exc:
        raise PaymentStateError(str(exc)) from exc

    pending_payments = list(
        (
            await session.scalars(
                select(Payment)
                .where(
                    Payment.order_id == order.id,
                    Payment.status == PaymentStatus.PENDING,
                )
                .with_for_update()
            )
        ).all()
    )
    for pending in pending_payments:
        pending.status = PaymentStatus.FAILED

    payment = Payment(
        order_id=order.id,
        provider="discount",
        provider_transaction_id=f"discount:{order.id}",
        amount=0,
        currency=order.currency,
        status=PaymentStatus.VERIFIED,
        verified_at=datetime.now(UTC),
        raw_reference="zero-price-order",
    )
    session.add(payment)
    order.status = OrderStatus.PAID
    await session.flush()
    return payment
