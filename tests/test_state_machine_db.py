from uuid import uuid4

import pytest
from sqlalchemy import select

from panelprimepasar.db import SessionFactory
from panelprimepasar.integrations.pasarguard import (
    PasarGuardAdmin,
    PasarGuardError,
    PasarGuardRole,
)
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    PasarGuardAccount,
    PaymentStatus,
    Plan,
    ProvisioningJob,
    ProvisioningStatus,
)
from panelprimepasar.services.payments import (
    create_pending_payment,
    verify_payment,
)
from panelprimepasar.services.provisioning import ProvisioningService


async def make_order(*, status: OrderStatus) -> tuple[Customer, Plan, Order]:
    marker = uuid4().hex
    customer = Customer(
        telegram_user_id=int(marker[:15], 16),
        telegram_username=f"user_{marker[:8]}",
        first_name="Test",
        last_name=None,
    )
    plan = Plan(
        name=f"plan-{marker}",
        quota_bytes=1_000_000_000_000,
        price_amount=200_000,
        currency="IRT",
        validity_days=None,
        is_active=True,
        sort_order=0,
    )
    order = Order(
        customer_id=customer.id,
        plan_id=plan.id,
        status=status,
        price_amount=plan.price_amount,
        currency=plan.currency,
        quota_bytes=plan.quota_bytes,
        validity_days=plan.validity_days,
        idempotency_key=f"test:{marker}",
    )
    return customer, plan, order


@pytest.mark.asyncio(loop_scope="session")
async def test_verified_payment_transitions_order_to_paid() -> None:
    async with SessionFactory() as session:
        customer, plan, order = await make_order(status=OrderStatus.AWAITING_PAYMENT)
        session.add_all([customer, plan])
        await session.flush()

        order.customer_id = customer.id
        order.plan_id = plan.id
        session.add(order)
        await session.flush()

        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="test-provider",
            raw_reference="reference-1",
        )
        verified = await verify_payment(
            session,
            payment_id=payment.id,
            provider_transaction_id=f"tx-{uuid4().hex}",
            verified_amount=order.price_amount,
            verified_currency=order.currency,
        )

        assert verified.status == PaymentStatus.VERIFIED
        assert order.status == OrderStatus.PAID
        assert verified.verified_at is not None
        await session.rollback()


class FakeProvisioningClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.ensure_calls = 0
        self.modify_calls = 0

    async def resolve_reseller_role(
        self,
        *,
        role_id: int | None,
        role_name: str | None,
    ) -> PasarGuardRole:
        if self.fail:
            raise PasarGuardError("simulated upstream failure")
        return PasarGuardRole(
            id=role_id or 7,
            name=role_name or "نمایندگان",
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
        self.ensure_calls += 1
        return PasarGuardAdmin(
            id=101,
            username=username,
            data_limit=data_limit,
            status="active",
            role=PasarGuardRole(id=role_id, name="نمایندگان", is_owner=False),
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
        self.modify_calls += 1
        return PasarGuardAdmin(
            id=admin_id,
            username="reseller",
            data_limit=data_limit,
            status=status or "active",
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_provisioning_is_locally_idempotent() -> None:
    client = FakeProvisioningClient()

    async with SessionFactory() as session:
        customer, plan, order = await make_order(status=OrderStatus.PAID)
        session.add_all([customer, plan])
        await session.flush()

        order.customer_id = customer.id
        order.plan_id = plan.id
        session.add(order)
        await session.flush()

        service = ProvisioningService(
            client=client,
            reseller_role_id=7,
            reseller_role_name=None,
        )
        first = await service.provision_paid_order(session, order_id=order.id)
        second = await service.provision_paid_order(session, order_id=order.id)

        account = await session.scalar(
            select(PasarGuardAccount).where(PasarGuardAccount.order_id == order.id)
        )

        assert first.success is True
        assert first.credentials is not None
        assert second.success is True
        assert second.already_provisioned is True
        assert client.ensure_calls == 1
        assert client.modify_calls == 1
        assert order.status == OrderStatus.COMPLETED
        assert account is not None
        assert account.pasarguard_admin_id == 101
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_provisioning_failure_is_persisted_in_state_machine() -> None:
    client = FakeProvisioningClient(fail=True)

    async with SessionFactory() as session:
        customer, plan, order = await make_order(status=OrderStatus.PAID)
        session.add_all([customer, plan])
        await session.flush()

        order.customer_id = customer.id
        order.plan_id = plan.id
        session.add(order)
        await session.flush()

        service = ProvisioningService(
            client=client,
            reseller_role_id=7,
            reseller_role_name=None,
        )
        outcome = await service.provision_paid_order(session, order_id=order.id)
        job = await session.scalar(
            select(ProvisioningJob).where(ProvisioningJob.order_id == order.id)
        )

        assert outcome.success is False
        assert order.status == OrderStatus.FAILED
        assert job is not None
        assert job.status == ProvisioningStatus.FAILED
        assert job.last_error_code == "PasarGuardError"
        await session.rollback()
