from uuid import uuid4

import pytest
from sqlalchemy import select

from panelprimepasar.db import SessionFactory
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    Plan,
    Wallet,
    WalletTransaction,
)
from panelprimepasar.services.wallets import (
    WalletStateError,
    credit_wallet,
    pay_order_with_wallet,
)


@pytest.mark.asyncio(loop_scope="session")
async def test_wallet_credit_is_idempotent() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"wallet_{marker[:8]}",
            first_name="Wallet",
            last_name=None,
        )
        session.add(customer)
        await session.flush()

        first = await credit_wallet(
            session,
            customer_id=customer.id,
            amount=150_000,
            currency="IRT",
            idempotency_key=f"credit:{marker}",
            reference="test",
        )
        second = await credit_wallet(
            session,
            customer_id=customer.id,
            amount=150_000,
            currency="IRT",
            idempotency_key=f"credit:{marker}",
            reference="test",
        )
        wallet = await session.scalar(
            select(Wallet).where(Wallet.customer_id == customer.id)
        )

        assert first.id == second.id
        assert wallet is not None
        assert wallet.balance == 150_000
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_wallet_payment_marks_order_paid_and_debits_once() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"walletpay_{marker[:8]}",
            first_name="Wallet",
            last_name="Pay",
        )
        plan = Plan(
            name=f"wallet-plan-{marker}",
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
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"wallet-order:{marker}",
        )
        session.add(order)
        await session.flush()

        await credit_wallet(
            session,
            customer_id=customer.id,
            amount=250_000,
            currency="IRT",
            idempotency_key=f"credit:{marker}",
        )
        first = await pay_order_with_wallet(
            session,
            customer_id=customer.id,
            order_id=order.id,
        )
        second = await pay_order_with_wallet(
            session,
            customer_id=customer.id,
            order_id=order.id,
        )
        wallet = await session.scalar(
            select(Wallet).where(Wallet.customer_id == customer.id)
        )
        debits = list(
            (
                await session.scalars(
                    select(WalletTransaction).where(
                        WalletTransaction.wallet_id == wallet.id,
                        WalletTransaction.kind == "debit",
                    )
                )
            ).all()
        ) if wallet is not None else []
        payments = list(
            (
                await session.scalars(
                    select(Payment).where(Payment.order_id == order.id)
                )
            ).all()
        )

        assert first.id == second.id
        assert first.status == PaymentStatus.VERIFIED
        assert first.provider == "wallet"
        assert order.status == OrderStatus.PAID
        assert wallet is not None
        assert wallet.balance == 150_000
        assert len(debits) == 1
        assert len(payments) == 1
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_wallet_payment_rejects_insufficient_balance() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"poor_{marker[:8]}",
            first_name="Low",
            last_name="Balance",
        )
        plan = Plan(
            name=f"poor-plan-{marker}",
            quota_bytes=50_000_000_000,
            price_amount=500_000,
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
            idempotency_key=f"poor-order:{marker}",
        )
        session.add(order)
        await session.flush()

        with pytest.raises(WalletStateError):
            await pay_order_with_wallet(
                session,
                customer_id=customer.id,
                order_id=order.id,
            )
        assert order.status == OrderStatus.AWAITING_PAYMENT
        await session.rollback()
