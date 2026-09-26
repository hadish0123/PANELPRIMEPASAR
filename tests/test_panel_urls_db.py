from uuid import uuid4

import pytest

from panelprimepasar.config import Settings
from panelprimepasar.db import SessionFactory
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    PasarGuardAccount,
    PasarGuardInstance,
    Plan,
)
from panelprimepasar.services.panel_urls import resolve_order_panel_url


@pytest.mark.asyncio(loop_scope="session")
async def test_panel_url_uses_assigned_pasarguard_instance() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"url_{marker[:8]}",
            first_name="URL",
            last_name=None,
        )
        plan = Plan(
            name=f"url-plan-{marker}",
            quota_bytes=100,
            price_amount=1,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        instance = PasarGuardInstance(
            name=f"instance-{marker}",
            base_url=f"https://assigned-{marker}.example/",
            api_key_env_var=f"PG_{marker}",
            bearer_token_env_var=None,
            reseller_role_name="reseller",
            reseller_role_id=7,
            weight=100,
            is_enabled=True,
        )
        session.add_all([customer, plan, instance])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            status=OrderStatus.COMPLETED,
            price_amount=1,
            currency="IRT",
            quota_bytes=100,
            validity_days=30,
            idempotency_key=f"url-order:{marker}",
        )
        session.add(order)
        await session.flush()
        account = PasarGuardAccount(
            customer_id=customer.id,
            order_id=order.id,
            pasarguard_instance_id=instance.id,
            pasarguard_admin_id=77,
            username=f"r_{marker[:16]}",
            role_id=7,
            role_name="reseller",
            quota_bytes=100,
            is_active=True,
        )
        session.add(account)
        await session.flush()

        resolved = await resolve_order_panel_url(
            session,
            settings=Settings(
                pasarguard_base_url="https://global.example"
            ),
            order_id=order.id,
        )

        assert resolved == f"https://assigned-{marker}.example"
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_panel_url_falls_back_to_global_for_legacy_account() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"legacy_{marker[:8]}",
            first_name="Legacy",
            last_name=None,
        )
        plan = Plan(
            name=f"legacy-plan-{marker}",
            quota_bytes=100,
            price_amount=1,
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
            status=OrderStatus.COMPLETED,
            price_amount=1,
            currency="IRT",
            quota_bytes=100,
            validity_days=30,
            idempotency_key=f"legacy-order:{marker}",
        )
        session.add(order)
        await session.flush()
        session.add(
            PasarGuardAccount(
                customer_id=customer.id,
                order_id=order.id,
                pasarguard_instance_id=None,
                pasarguard_admin_id=88,
                username=f"legacy_{marker[:16]}",
                role_id=7,
                role_name="reseller",
                quota_bytes=100,
                is_active=True,
            )
        )
        await session.flush()

        resolved = await resolve_order_panel_url(
            session,
            settings=Settings(
                pasarguard_base_url="https://global.example/"
            ),
            order_id=order.id,
        )

        assert resolved == "https://global.example"
        await session.rollback()
