from uuid import uuid4

import pytest
from sqlalchemy import func, select

from panelprimepasar.db import SessionFactory
from panelprimepasar.models import Customer, Order, OrderStatus, Payment, PaymentStatus, Plan
from panelprimepasar.services.payments import approve_manual_order


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
