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
from panelprimepasar.services.maintenance import expire_due_subscriptions


class FakeMaintenanceClient:
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
                "status": status,
                "note": note,
            }
        )
        return PasarGuardAdmin(
            id=admin_id,
            username="expired-reseller",
            status=status or "active",
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_expiry_disables_pasarguard_account() -> None:
    marker = uuid4().hex
    now = datetime.now(UTC)

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:14], 16),
            telegram_username=f"expiry_{marker[:8]}",
            first_name="Expiry",
            last_name=None,
        )
        plan = Plan(
            name=f"expiry-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=20_000,
            currency="IRT",
            validity_days=1,
            is_active=True,
            sort_order=0,
        )
        session.add_all([customer, plan])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            kind=OrderKind.NEW,
            status=OrderStatus.COMPLETED,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=1,
            idempotency_key=f"expiry:{marker}",
        )
        session.add(order)
        await session.flush()

        account = PasarGuardAccount(
            customer_id=customer.id,
            order_id=order.id,
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
            source_order_id=order.id,
            status=SubscriptionStatus.ACTIVE.value,
            quota_bytes=plan.quota_bytes,
            starts_at=now - timedelta(days=2),
            expires_at=now - timedelta(minutes=1),
            auto_renew=False,
        )
        session.add(subscription)
        await session.flush()

        client = FakeMaintenanceClient()
        results = await expire_due_subscriptions(
            session,
            client=client,
            now=now,
        )

        assert len(results) == 1
        assert results[0].success is True
        assert subscription.status == SubscriptionStatus.EXPIRED.value
        assert account.is_active is False
        assert client.calls[0]["status"] == "disabled"
        await session.rollback()
