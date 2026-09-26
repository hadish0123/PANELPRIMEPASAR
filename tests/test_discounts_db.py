from uuid import uuid4

import pytest
from sqlalchemy import select

from panelprimepasar.db import SessionFactory
from panelprimepasar.models import (
    Customer,
    DiscountCode,
    DiscountKind,
    DiscountRedemption,
    DiscountRedemptionStatus,
    Order,
    OrderStatus,
    PaymentStatus,
    Plan,
)
from panelprimepasar.services.discounts import (
    DiscountStateError,
    reserve_discount_for_order,
)
from panelprimepasar.services.payments import (
    cancel_unpaid_order,
    create_pending_payment,
    settle_zero_price_order,
    verify_payment,
)


async def _build_order(*, marker: str, price: int) -> tuple[Customer, Plan, Order]:
    customer = Customer(
        telegram_user_id=int(marker[:15], 16),
        telegram_username=f"discount_{marker[:8]}",
        first_name="Discount",
        last_name=None,
    )
    plan = Plan(
        name=f"discount-plan-{marker}",
        quota_bytes=100_000_000_000,
        price_amount=price,
        currency="IRT",
        validity_days=30,
        is_active=True,
        sort_order=0,
    )
    return customer, plan, Order(
        customer_id=customer.id,
        plan_id=plan.id,
        status=OrderStatus.AWAITING_PAYMENT,
        price_amount=price,
        currency="IRT",
        quota_bytes=plan.quota_bytes,
        validity_days=30,
        idempotency_key=f"discount-order:{marker}",
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_discount_reservation_redeems_with_verified_payment() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"discount_{marker[:8]}",
            first_name="Discount",
            last_name=None,
        )
        plan = Plan(
            name=f"discount-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=200_000,
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
            validity_days=30,
            idempotency_key=f"discount-order:{marker}",
        )
        discount = DiscountCode(
            code=f"OFF{marker[:6].upper()}",
            kind=DiscountKind.PERCENT.value,
            value_amount=None,
            value_percent=25,
            max_uses=10,
            used_count=0,
            is_active=True,
        )
        session.add_all([order, discount])
        await session.flush()

        redemption = await reserve_discount_for_order(
            session,
            customer_id=customer.id,
            order_id=order.id,
            raw_code=discount.code.lower(),
        )
        assert redemption.amount == 50_000
        assert order.price_amount == 150_000
        assert order.discount_amount == 50_000
        assert discount.used_count == 1

        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
        )
        verified = await verify_payment(
            session,
            payment_id=payment.id,
            provider_transaction_id=f"test:{payment.id}",
            verified_amount=150_000,
            verified_currency="IRT",
        )
        await session.refresh(redemption)

        assert verified.status == PaymentStatus.VERIFIED
        assert redemption.status == DiscountRedemptionStatus.REDEEMED.value
        assert order.status == OrderStatus.PAID
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_cancel_unpaid_order_releases_discount() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"release_{marker[:8]}",
            first_name="Release",
            last_name=None,
        )
        plan = Plan(
            name=f"release-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=100_000,
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
            price_amount=100_000,
            currency="IRT",
            quota_bytes=plan.quota_bytes,
            validity_days=30,
            idempotency_key=f"release-order:{marker}",
        )
        discount = DiscountCode(
            code=f"FIX{marker[:6].upper()}",
            kind=DiscountKind.FIXED.value,
            value_amount=30_000,
            value_percent=None,
            max_uses=1,
            used_count=0,
            is_active=True,
        )
        session.add_all([order, discount])
        await session.flush()

        redemption = await reserve_discount_for_order(
            session,
            customer_id=customer.id,
            order_id=order.id,
            raw_code=discount.code,
        )
        assert order.price_amount == 70_000
        assert discount.used_count == 1

        await cancel_unpaid_order(session, order_id=order.id)
        await session.refresh(redemption)

        assert order.status == OrderStatus.CANCELED
        assert order.price_amount == 100_000
        assert order.discount_amount == 0
        assert order.discount_code_id is None
        assert discount.used_count == 0
        assert redemption.status == DiscountRedemptionStatus.RELEASED.value
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_full_discount_settles_zero_price_order() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"free_{marker[:8]}",
            first_name="Free",
            last_name=None,
        )
        plan = Plan(
            name=f"free-plan-{marker}",
            quota_bytes=50_000_000_000,
            price_amount=80_000,
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
            price_amount=80_000,
            currency="IRT",
            quota_bytes=plan.quota_bytes,
            validity_days=30,
            idempotency_key=f"free-order:{marker}",
        )
        discount = DiscountCode(
            code=f"FREE{marker[:6].upper()}",
            kind=DiscountKind.PERCENT.value,
            value_amount=None,
            value_percent=100,
            max_uses=None,
            used_count=0,
            is_active=True,
        )
        session.add_all([order, discount])
        await session.flush()

        redemption = await reserve_discount_for_order(
            session,
            customer_id=customer.id,
            order_id=order.id,
            raw_code=discount.code,
        )
        assert order.price_amount == 0

        payment = await settle_zero_price_order(session, order_id=order.id)
        await session.refresh(redemption)

        assert payment.amount == 0
        assert payment.provider == "discount"
        assert payment.status == PaymentStatus.VERIFIED
        assert redemption.status == DiscountRedemptionStatus.REDEEMED.value
        assert order.status == OrderStatus.PAID
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_discount_usage_limit_is_enforced() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"limit_{marker[:8]}",
            first_name="Limit",
            last_name=None,
        )
        plan = Plan(
            name=f"limit-plan-{marker}",
            quota_bytes=10_000_000_000,
            price_amount=10_000,
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
            price_amount=10_000,
            currency="IRT",
            quota_bytes=plan.quota_bytes,
            validity_days=30,
            idempotency_key=f"limit-order:{marker}",
        )
        discount = DiscountCode(
            code=f"MAX{marker[:6].upper()}",
            kind=DiscountKind.FIXED.value,
            value_amount=1_000,
            value_percent=None,
            max_uses=1,
            used_count=1,
            is_active=True,
        )
        session.add_all([order, discount])
        await session.flush()

        with pytest.raises(DiscountStateError):
            await reserve_discount_for_order(
                session,
                customer_id=customer.id,
                order_id=order.id,
                raw_code=discount.code,
            )

        redemptions = list(
            (
                await session.scalars(
                    select(DiscountRedemption).where(
                        DiscountRedemption.order_id == order.id
                    )
                )
            ).all()
        )
        assert redemptions == []
        await session.rollback()
