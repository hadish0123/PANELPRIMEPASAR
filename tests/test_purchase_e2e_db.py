from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from panelprimepasar.db import SessionFactory
from panelprimepasar.integrations.pasarguard import PasarGuardAdmin, PasarGuardRole
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
from panelprimepasar.services.payments import approve_manual_order
from panelprimepasar.services.provisioning import ProvisioningService
from panelprimepasar.services.subscriptions import apply_paid_lifecycle_order


class PurchaseClient:
    def __init__(self) -> None:
        self.ensure_calls = 0
        self.data_limits: list[int | None] = []
        self.sync_data_limits: list[int | None] = []

    async def resolve_reseller_role(
        self,
        *,
        role_id: int | None,
        role_name: str | None,
    ) -> PasarGuardRole:
        return PasarGuardRole(
            id=role_id or 7,
            name=role_name or "reseller",
            is_owner=False,
        )

    async def ensure_admin(
        self,
        *,
        username: str,
        password: str,
        role_id: int,
        data_limit: int | None,
        note: str | None = None,
    ) -> PasarGuardAdmin:
        del password, note
        self.ensure_calls += 1
        self.data_limits.append(data_limit)
        return PasarGuardAdmin(
            id=9001,
            username=username,
            data_limit=data_limit,
            status="active",
            role=PasarGuardRole(
                id=role_id,
                name="reseller",
                is_owner=False,
            ),
        )

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
        del password, role_id, note
        self.sync_data_limits.append(data_limit)
        return PasarGuardAdmin(
            id=admin_id,
            username="reseller",
            data_limit=data_limit,
            status=status or "active",
        )


class LifecycleClient:
    def __init__(self) -> None:
        self.modify_calls = 0
        self.last_data_limit: int | None = None

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
        del password, role_id, note
        self.modify_calls += 1
        self.last_data_limit = data_limit
        return PasarGuardAdmin(
            id=admin_id,
            username="reseller",
            data_limit=data_limit,
            status=status or "active",
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_purchase_payment_to_reseller_provisioning_is_idempotent() -> None:
    marker = uuid4().hex
    client = PurchaseClient()

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"e2e_{marker[:8]}",
            first_name="E2E",
            last_name=None,
        )
        plan = Plan(
            name=f"e2e-plan-{marker}",
            quota_bytes=300_000_000_000,
            price_amount=180_000,
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
            kind=OrderKind.NEW,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"e2e-purchase:{marker}",
        )
        session.add(order)
        await session.flush()

        payment = await approve_manual_order(
            session,
            order_id=order.id,
            actor_telegram_id=123456,
        )
        assert order.status == OrderStatus.PAID

        service = ProvisioningService(
            client=client,
            reseller_role_id=7,
            reseller_role_name=None,
        )
        first = await service.provision_paid_order(
            session,
            order_id=order.id,
        )
        second = await service.provision_paid_order(
            session,
            order_id=order.id,
        )
        repeated_payment = await approve_manual_order(
            session,
            order_id=order.id,
            actor_telegram_id=123456,
        )

        account = await session.scalar(
            select(PasarGuardAccount).where(
                PasarGuardAccount.order_id == order.id
            )
        )
        subscription = await session.scalar(
            select(Subscription).where(
                Subscription.source_order_id == order.id
            )
        )

        assert first.success is True
        assert first.credentials is not None
        assert second.success is True
        assert second.already_provisioned is True
        assert repeated_payment.id == payment.id
        assert client.ensure_calls == 1
        assert client.data_limits == [plan.quota_bytes]
        assert client.sync_data_limits == [plan.quota_bytes]
        assert order.status == OrderStatus.COMPLETED
        assert account is not None
        assert account.quota_bytes == plan.quota_bytes
        assert subscription is not None
        assert subscription.status == SubscriptionStatus.ACTIVE.value
        assert subscription.plan_id == plan.id
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_renewal_payment_to_lifecycle_fulfillment_is_idempotent() -> None:
    marker = uuid4().hex
    client = LifecycleClient()
    initial_expiry = datetime.now(UTC) + timedelta(days=5)

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"renew_e2e_{marker[:8]}",
            first_name="Renew",
            last_name=None,
        )
        base_plan = Plan(
            name=f"base-{marker}",
            quota_bytes=250_000_000_000,
            price_amount=100_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        renewal_plan = Plan(
            name=f"renew-{marker}",
            quota_bytes=250_000_000_000,
            price_amount=70_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=1,
        )
        session.add_all([customer, base_plan, renewal_plan])
        await session.flush()

        source_order = Order(
            customer_id=customer.id,
            plan_id=base_plan.id,
            kind=OrderKind.NEW,
            status=OrderStatus.COMPLETED,
            price_amount=base_plan.price_amount,
            currency=base_plan.currency,
            quota_bytes=base_plan.quota_bytes,
            validity_days=base_plan.validity_days,
            idempotency_key=f"source:{marker}",
        )
        session.add(source_order)
        await session.flush()

        account = PasarGuardAccount(
            customer_id=customer.id,
            order_id=source_order.id,
            pasarguard_admin_id=42,
            username=f"r_{marker[:16]}",
            role_id=7,
            role_name="reseller",
            quota_bytes=base_plan.quota_bytes,
            is_active=True,
        )
        session.add(account)
        await session.flush()

        subscription = Subscription(
            customer_id=customer.id,
            plan_id=base_plan.id,
            pasar_guard_account_id=account.id,
            source_order_id=source_order.id,
            status=SubscriptionStatus.ACTIVE.value,
            quota_bytes=base_plan.quota_bytes,
            starts_at=datetime.now(UTC) - timedelta(days=25),
            expires_at=initial_expiry,
            auto_renew=False,
        )
        session.add(subscription)
        await session.flush()

        renewal = Order(
            customer_id=customer.id,
            plan_id=renewal_plan.id,
            kind=OrderKind.RENEWAL,
            target_subscription_id=subscription.id,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=renewal_plan.price_amount,
            currency=renewal_plan.currency,
            quota_bytes=renewal_plan.quota_bytes,
            validity_days=renewal_plan.validity_days,
            idempotency_key=f"renewal:{marker}",
        )
        session.add(renewal)
        await session.flush()

        payment = await approve_manual_order(
            session,
            order_id=renewal.id,
            actor_telegram_id=123456,
        )
        assert renewal.status == OrderStatus.PAID

        first = await apply_paid_lifecycle_order(
            session,
            order_id=renewal.id,
            client=client,
        )
        second = await apply_paid_lifecycle_order(
            session,
            order_id=renewal.id,
            client=client,
        )
        repeated_payment = await approve_manual_order(
            session,
            order_id=renewal.id,
            actor_telegram_id=123456,
        )

        assert first.success is True
        assert second.success is True
        assert repeated_payment.id == payment.id
        assert client.modify_calls == 1
        assert renewal.status == OrderStatus.COMPLETED
        assert subscription.plan_id == renewal_plan.id
        assert subscription.expires_at is None
        assert subscription.quota_bytes == renewal_plan.quota_bytes
        assert client.last_data_limit == renewal_plan.quota_bytes
        await session.rollback()
