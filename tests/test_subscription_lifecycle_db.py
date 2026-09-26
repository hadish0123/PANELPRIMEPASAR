from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from panelprimepasar.db import SessionFactory
from panelprimepasar.integrations.pasarguard import PasarGuardAdmin
from panelprimepasar.models import (
    Customer,
    Order,
    OrderKind,
    OrderStatus,
    PasarGuardAccount,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from panelprimepasar.services.subscriptions import apply_paid_lifecycle_order


class FakeLifecycleClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def modify_admin_by_id(
        self,
        admin_id: int,
        *,
        password: str | None = None,
        role_id: int | None = None,
        data_limit: int | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> PasarGuardAdmin:
        self.calls.append(
            {
                "admin_id": admin_id,
                "data_limit": data_limit,
                "status": status,
                "note": note,
            }
        )
        return PasarGuardAdmin(
            id=admin_id,
            username="reseller",
            data_limit=data_limit,
            status=status or "active",
        )


async def _seed_subscription(
    *,
    expires_at: datetime | None,
) -> tuple[Customer, Plan, PasarGuardAccount, Subscription]:
    marker = uuid4().hex
    customer = Customer(
        telegram_user_id=int(marker[:14], 16),
        telegram_username=f"lifecycle_{marker[:8]}",
        first_name="Life",
        last_name=None,
    )
    plan = Plan(
        name=f"base-{marker}",
        quota_bytes=500_000_000_000,
        price_amount=100_000,
        currency="IRT",
        validity_days=30,
        is_active=True,
        sort_order=0,
    )

    async with SessionFactory() as session:
        session.add_all([customer, plan])
        await session.flush()

        source_order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            kind=OrderKind.NEW,
            status=OrderStatus.COMPLETED,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"source:{marker}",
        )
        session.add(source_order)
        await session.flush()

        account = PasarGuardAccount(
            customer_id=customer.id,
            order_id=source_order.id,
            pasarguard_admin_id=int(marker[:9], 16),
            username=f"r{marker[:20]}",
            role_id=7,
            role_name="representative",
            quota_bytes=plan.quota_bytes,
            is_active=True,
        )
        session.add(account)
        await session.flush()

        subscription = Subscription(
            customer_id=customer.id,
            plan_id=plan.id,
            pasar_guard_account_id=account.id,
            source_order_id=source_order.id,
            status=SubscriptionStatus.ACTIVE.value,
            quota_bytes=plan.quota_bytes,
            starts_at=datetime.now(UTC) - timedelta(days=10),
            expires_at=expires_at,
            auto_renew=False,
        )
        session.add(subscription)
        await session.commit()

        return customer, plan, account, subscription


@pytest.mark.asyncio(loop_scope="session")
async def test_topup_increases_pasarguard_quota() -> None:
    now = datetime.now(UTC)
    customer, plan, account, subscription = await _seed_subscription(
        expires_at=now + timedelta(days=20)
    )
    marker = uuid4().hex

    async with SessionFactory() as session:
        topup_plan = Plan(
            name=f"topup-{marker}",
            quota_bytes=250_000_000_000,
            price_amount=50_000,
            currency="IRT",
            validity_days=None,
            is_active=True,
            sort_order=0,
        )
        session.add(topup_plan)
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=topup_plan.id,
            kind=OrderKind.TOPUP,
            target_subscription_id=subscription.id,
            status=OrderStatus.PAID,
            price_amount=topup_plan.price_amount,
            currency=topup_plan.currency,
            quota_bytes=topup_plan.quota_bytes,
            validity_days=None,
            idempotency_key=f"topup:{marker}",
        )
        session.add(order)
        await session.flush()

        client = FakeLifecycleClient()
        outcome = await apply_paid_lifecycle_order(
            session,
            order_id=order.id,
            client=client,
        )
        refreshed = await session.get(Subscription, subscription.id)
        refreshed_account = await session.get(PasarGuardAccount, account.id)

        assert outcome.success is True
        assert order.status == OrderStatus.COMPLETED
        assert refreshed is not None
        assert refreshed_account is not None
        assert refreshed.quota_bytes == 750_000_000_000
        assert refreshed_account.quota_bytes == 750_000_000_000
        assert client.calls[0]["data_limit"] == 750_000_000_000
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_renewal_extends_from_existing_future_expiry() -> None:
    current_expiry = datetime.now(UTC) + timedelta(days=10)
    customer, _, _, subscription = await _seed_subscription(
        expires_at=current_expiry
    )
    marker = uuid4().hex

    async with SessionFactory() as session:
        renewal_plan = Plan(
            name=f"renew-{marker}",
            quota_bytes=500_000_000_000,
            price_amount=80_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        session.add(renewal_plan)
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=renewal_plan.id,
            kind=OrderKind.RENEWAL,
            target_subscription_id=subscription.id,
            status=OrderStatus.PAID,
            price_amount=renewal_plan.price_amount,
            currency=renewal_plan.currency,
            quota_bytes=renewal_plan.quota_bytes,
            validity_days=renewal_plan.validity_days,
            idempotency_key=f"renew:{marker}",
        )
        session.add(order)
        await session.flush()

        client = FakeLifecycleClient()
        outcome = await apply_paid_lifecycle_order(
            session,
            order_id=order.id,
            client=client,
        )
        refreshed = await session.get(Subscription, subscription.id)

        assert outcome.success is True
        assert refreshed is not None
        assert refreshed.expires_at is not None
        expected = current_expiry + timedelta(days=30)
        assert abs((refreshed.expires_at - expected).total_seconds()) < 2
        assert refreshed.plan_id == renewal_plan.id
        assert refreshed.status == SubscriptionStatus.ACTIVE.value
        await session.rollback()
