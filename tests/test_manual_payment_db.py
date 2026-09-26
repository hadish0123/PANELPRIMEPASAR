from uuid import uuid4

import pytest
from sqlalchemy import func, select

from panelprimepasar.db import SessionFactory
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    Payment,
    PaymentMethodConfig,
    PaymentStatus,
    Plan,
)
from panelprimepasar.services.payments import (
    PaymentStateError,
    approve_manual_order,
    cancel_unpaid_order,
    create_pending_payment,
    reject_pending_manual_payment,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_manual_approval_is_idempotent() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"user_{marker[:8]}",
            first_name="Test",
            last_name=None,
        )
        plan = Plan(
            name=f"manual-plan-{marker}",
            quota_bytes=500_000_000_000,
            price_amount=100_000,
            currency="IRT",
            validity_days=None,
            is_active=True,
            sort_order=0,
        )
        session.add_all([customer, plan])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=None,
            idempotency_key=f"manual-test:{marker}",
        )
        session.add(order)
        await session.flush()

        first = await approve_manual_order(
            session,
            order_id=order.id,
            actor_telegram_id=123456,
        )
        second = await approve_manual_order(
            session,
            order_id=order.id,
            actor_telegram_id=123456,
        )

        payment_count = await session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == order.id)
        )

        assert first.id == second.id
        assert first.status == PaymentStatus.VERIFIED
        assert first.provider_transaction_id == f"manual:{first.id}"
        assert order.status == OrderStatus.PAID
        assert payment_count == 1
        await session.rollback()



@pytest.mark.asyncio(loop_scope="session")
async def test_reject_pending_manual_payment_keeps_order_payable() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"reject_{marker[:8]}",
            first_name="Reject",
            last_name=None,
        )
        plan = Plan(
            name=f"reject-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=50_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        session.add_all([customer, plan])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"reject-test:{marker}",
        )
        session.add(order)
        await session.flush()

        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
            raw_reference="telegram:photo:test",
        )
        rejected = await reject_pending_manual_payment(
            session,
            order_id=order.id,
        )

        assert rejected.id == payment.id
        assert rejected.status == PaymentStatus.FAILED
        assert order.status == OrderStatus.AWAITING_PAYMENT

        replacement = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
            raw_reference="telegram:photo:replacement",
        )
        assert replacement.id != rejected.id
        assert replacement.status == PaymentStatus.PENDING
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_cancel_unpaid_order_fails_pending_payments() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"cancel_{marker[:8]}",
            first_name="Cancel",
            last_name=None,
        )
        plan = Plan(
            name=f"cancel-plan-{marker}",
            quota_bytes=200_000_000_000,
            price_amount=75_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        session.add_all([customer, plan])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"cancel-test:{marker}",
        )
        session.add(order)
        await session.flush()

        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
        )
        canceled = await cancel_unpaid_order(session, order_id=order.id)

        assert canceled.status == OrderStatus.CANCELED
        assert payment.status == PaymentStatus.FAILED

        with pytest.raises(PaymentStateError):
            await create_pending_payment(
                session,
                order_id=order.id,
                provider="manual",
            )
        await session.rollback()



@pytest.mark.asyncio(loop_scope="session")
async def test_manual_card_method_approval_reuses_selected_payment() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"card_{marker[:8]}",
            first_name="Card",
            last_name=None,
        )
        plan = Plan(
            name=f"card-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=45_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        method = PaymentMethodConfig(
            slug=f"card{marker[:8]}",
            kind="manual_card",
            display_name="کارت به کارت",
            is_enabled=True,
            sandbox=False,
            sort_order=0,
            public_config_json=(
                '{"card_holder":"Test","card_number":"6037991234567890"}'
            ),
            secret_config_encrypted=None,
        )
        session.add_all([customer, plan, method])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"card-method:{marker}",
        )
        session.add(order)
        await session.flush()

        selected = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
            payment_method_id=method.id,
            raw_reference="telegram:photo:selected-card",
        )
        approved = await approve_manual_order(
            session,
            order_id=order.id,
            actor_telegram_id=999,
        )
        payment_count = await session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == order.id)
        )

        assert approved.id == selected.id
        assert approved.payment_method_id == method.id
        assert approved.status == PaymentStatus.VERIFIED
        assert payment_count == 1
        await session.rollback()
