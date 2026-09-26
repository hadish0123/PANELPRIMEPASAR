from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import Customer, Order, OrderStatus, PaymentStatus, Plan
from panelprimepasar.services.orders import (
    OrderStateError,
    cancel_order,
    get_or_create_checkout_order,
)
from panelprimepasar.services.payments import (
    PaymentStateError,
    approve_manual_order,
    create_pending_payment,
    fail_payment,
    verify_payment,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def purchase(session: AsyncSession) -> tuple[Customer, Plan, Order]:
    customer = Customer(telegram_user_id=int(uuid4().hex[:12], 16))
    plan = Plan(name=uuid4().hex, quota_bytes=10**12, price_amount=200000, currency="IRT")
    session.add_all([customer, plan])
    await session.flush()
    order, _ = await get_or_create_checkout_order(
        session, customer=customer, plan=plan, idempotency_key=uuid4().hex
    )
    return customer, plan, order


async def test_blocked_customer_and_disabled_plan(db_session: AsyncSession) -> None:
    customer, plan, _ = await purchase(db_session)
    customer.is_blocked = True
    await db_session.flush()
    with pytest.raises(OrderStateError, match="blocked"):
        await get_or_create_checkout_order(
            db_session, customer=customer, plan=plan, idempotency_key=uuid4().hex
        )
    customer.is_blocked = False
    plan.is_active = False
    await db_session.flush()
    with pytest.raises(OrderStateError, match="no longer active"):
        await get_or_create_checkout_order(
            db_session, customer=customer, plan=plan, idempotency_key=uuid4().hex
        )


async def test_canceled_order_cannot_be_paid(db_session: AsyncSession) -> None:
    _, _, order = await purchase(db_session)
    payment = await create_pending_payment(db_session, order_id=order.id, provider="manual")
    await cancel_order(db_session, order_id=order.id)
    with pytest.raises(PaymentStateError):
        await verify_payment(
            db_session,
            payment_id=payment.id,
            provider_transaction_id=uuid4().hex,
            verified_amount=order.price_amount,
            verified_currency=order.currency,
        )
    assert order.status == OrderStatus.CANCELED
    assert payment.status == PaymentStatus.FAILED


async def test_manual_approval_preserves_receipt_and_is_idempotent(
    db_session: AsyncSession,
) -> None:
    _, _, order = await purchase(db_session)
    original = await create_pending_payment(
        db_session, order_id=order.id, provider="manual", raw_reference="telegram:photo:receipt"
    )
    first = await approve_manual_order(db_session, order_id=order.id, actor_telegram_id=123)
    second = await approve_manual_order(db_session, order_id=order.id, actor_telegram_id=456)
    assert first.id == second.id == original.id
    assert first.raw_reference == "telegram:photo:receipt"
    assert order.status == OrderStatus.PAID
    with pytest.raises(OrderStateError):
        await cancel_order(db_session, order_id=order.id)


async def test_amount_currency_and_duplicate_transaction_checks(db_session: AsyncSession) -> None:
    _, _, order = await purchase(db_session)
    payment = await create_pending_payment(db_session, order_id=order.id, provider="manual")
    for amount, currency in ((order.price_amount - 1, "IRT"), (order.price_amount, "IRR")):
        with pytest.raises(PaymentStateError):
            await verify_payment(
                db_session,
                payment_id=payment.id,
                provider_transaction_id="reference",
                verified_amount=amount,
                verified_currency=currency,
            )
    await verify_payment(
        db_session,
        payment_id=payment.id,
        provider_transaction_id="reference",
        verified_amount=order.price_amount,
        verified_currency="IRT",
    )
    _, _, other = await purchase(db_session)
    other_payment = await create_pending_payment(db_session, order_id=other.id, provider="manual")
    with pytest.raises(PaymentStateError, match="another payment"):
        await verify_payment(
            db_session,
            payment_id=other_payment.id,
            provider_transaction_id="reference",
            verified_amount=other.price_amount,
            verified_currency="IRT",
        )


async def test_one_payment_success_prevents_second_charge(db_session: AsyncSession) -> None:
    _, _, order = await purchase(db_session)
    first = await create_pending_payment(db_session, order_id=order.id, provider="first")
    second = await create_pending_payment(db_session, order_id=order.id, provider="second")
    await verify_payment(
        db_session,
        payment_id=first.id,
        provider_transaction_id=uuid4().hex,
        verified_amount=order.price_amount,
        verified_currency="IRT",
    )
    assert second.status == PaymentStatus.FAILED
    with pytest.raises(PaymentStateError):
        await verify_payment(
            db_session,
            payment_id=second.id,
            provider_transaction_id=uuid4().hex,
            verified_amount=order.price_amount,
            verified_currency="IRT",
        )


async def test_refunded_payment_cannot_be_rejected(db_session: AsyncSession) -> None:
    _, _, order = await purchase(db_session)
    payment = await create_pending_payment(db_session, order_id=order.id, provider="manual")
    payment.status = PaymentStatus.REFUNDED
    await db_session.flush()
    with pytest.raises(PaymentStateError):
        await fail_payment(db_session, payment_id=payment.id)
