from uuid import uuid4

import pytest

from panelprimepasar.config import Settings
from panelprimepasar.db import SessionFactory
from panelprimepasar.models import PasarGuardAccount, PasarGuardInstance
from panelprimepasar.services.pasarguard_instances import (
    PasarGuardInstanceRouter,
    build_instance_client,
    weighted_instance_order,
)


class FakePasarGuardClient:
    health_by_url: dict[str, bool] = {}
    closed_urls: list[str] = []

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        bearer_token: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.bearer_token = bearer_token
        self.timeout_seconds = timeout_seconds

    async def health(self) -> bool:
        return self.health_by_url.get(self.base_url, False)

    async def close(self) -> None:
        self.closed_urls.append(self.base_url)


def _instance(*, name: str, base_url: str, env_var: str, weight: int = 100) -> PasarGuardInstance:
    return PasarGuardInstance(
        id=uuid4(),
        name=name,
        base_url=base_url,
        api_key_env_var=env_var,
        bearer_token_env_var=None,
        reseller_role_name="reseller",
        reseller_role_id=None,
        weight=weight,
        is_enabled=True,
    )


def test_weighted_instance_order_is_stable_and_skips_zero_weight() -> None:
    first = _instance(
        name="first",
        base_url="https://first.example",
        env_var="FIRST_KEY",
        weight=100,
    )
    second = _instance(
        name="second",
        base_url="https://second.example",
        env_var="SECOND_KEY",
        weight=200,
    )
    disabled_weight = _instance(
        name="zero",
        base_url="https://zero.example",
        env_var="ZERO_KEY",
        weight=0,
    )

    one = weighted_instance_order(
        [first, second, disabled_weight],
        routing_key="same-order",
    )
    two = weighted_instance_order(
        [second, disabled_weight, first],
        routing_key="same-order",
    )

    assert [item.id for item in one] == [item.id for item in two]
    assert disabled_weight.id not in {item.id for item in one}


def test_instance_client_resolves_secret_from_named_environment_variable() -> None:
    instance = _instance(
        name="primary",
        base_url="https://primary.example",
        env_var="PRIMARY_KEY",
    )
    settings = Settings()

    client = build_instance_client(
        settings,
        instance,
        environment={"PRIMARY_KEY": "secret-value"},
        client_builder=FakePasarGuardClient,
    )

    assert client.base_url == "https://primary.example"
    assert client.api_key == "secret-value"
    assert client.bearer_token is None


@pytest.mark.asyncio(loop_scope="session")
async def test_router_fails_over_to_next_healthy_instance() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        first = _instance(
            name=f"first-{marker}",
            base_url=f"https://first-{marker}.example",
            env_var=f"FIRST_{marker}",
            weight=100,
        )
        second = _instance(
            name=f"second-{marker}",
            base_url=f"https://second-{marker}.example",
            env_var=f"SECOND_{marker}",
            weight=100,
        )
        session.add_all([first, second])
        await session.flush()

        ordered = weighted_instance_order(
            [first, second],
            routing_key=marker,
        )
        unhealthy, healthy = ordered
        FakePasarGuardClient.health_by_url = {
            unhealthy.base_url: False,
            healthy.base_url: True,
        }
        FakePasarGuardClient.closed_urls = []

        router = PasarGuardInstanceRouter(
            settings=Settings(),
            environment={
                first.api_key_env_var or "": "first-secret",
                second.api_key_env_var or "": "second-secret",
            },
            client_builder=FakePasarGuardClient,
        )
        target = await router.select_for_new_order(
            session,
            routing_key=marker,
        )

        assert target.instance_id == healthy.id
        assert unhealthy.last_health_ok is False
        assert healthy.last_health_ok is True
        assert unhealthy.base_url in FakePasarGuardClient.closed_urls
        await target.client.close()
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_existing_account_keeps_assigned_instance_even_when_disabled() -> None:
    marker = uuid4().hex
    async with SessionFactory() as session:
        instance = _instance(
            name=f"assigned-{marker}",
            base_url=f"https://assigned-{marker}.example",
            env_var=f"ASSIGNED_{marker}",
        )
        instance.is_enabled = False
        session.add(instance)
        await session.flush()

        account = PasarGuardAccount(
            customer_id=uuid4(),
            order_id=uuid4(),
            pasarguard_instance_id=instance.id,
            pasarguard_admin_id=42,
            username=f"r_{marker}",
            role_id=3,
            role_name="reseller",
            quota_bytes=100,
            is_active=True,
        )

        router = PasarGuardInstanceRouter(
            settings=Settings(),
            environment={instance.api_key_env_var or "": "assigned-secret"},
            client_builder=FakePasarGuardClient,
        )
        target = await router.target_for_account(
            session,
            account=account,
        )

        assert target.instance_id == instance.id
        assert target.client.base_url == instance.base_url
        await target.client.close()
        await session.rollback()
