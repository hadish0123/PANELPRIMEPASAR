import hashlib
import math
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings
from panelprimepasar.integrations.factory import build_pasarguard_client
from panelprimepasar.integrations.pasarguard import (
    PasarGuardClient,
    PasarGuardConfigurationError,
)
from panelprimepasar.models import PasarGuardAccount, PasarGuardInstance


ClientBuilder = Callable[..., PasarGuardClient]


@dataclass(frozen=True, slots=True)
class PasarGuardTarget:
    instance_id: UUID | None
    name: str
    client: PasarGuardClient
    reseller_role_id: int | None
    reseller_role_name: str | None


def _routing_score(*, key: str, instance_id: UUID, weight: int) -> float:
    if weight <= 0:
        return math.inf
    digest = hashlib.sha256(f"{key}:{instance_id}".encode()).digest()
    number = int.from_bytes(digest[:8], "big")
    unit = (number + 1) / ((1 << 64) + 1)
    return -math.log(unit) / weight


def weighted_instance_order(
    instances: Sequence[PasarGuardInstance],
    *,
    routing_key: str,
) -> list[PasarGuardInstance]:
    return sorted(
        (instance for instance in instances if instance.weight > 0),
        key=lambda instance: (
            _routing_score(
                key=routing_key,
                instance_id=instance.id,
                weight=instance.weight,
            ),
            str(instance.id),
        ),
    )


def build_instance_client(
    settings: Settings,
    instance: PasarGuardInstance,
    *,
    environment: Mapping[str, str] | None = None,
    client_builder: ClientBuilder = PasarGuardClient,
) -> PasarGuardClient:
    env = os.environ if environment is None else environment
    api_key = (
        env.get(instance.api_key_env_var)
        if instance.api_key_env_var
        else None
    )
    bearer_token = (
        env.get(instance.bearer_token_env_var)
        if instance.bearer_token_env_var
        else None
    )

    if not api_key and not bearer_token:
        configured = [
            name
            for name in (
                instance.api_key_env_var,
                instance.bearer_token_env_var,
            )
            if name
        ]
        if configured:
            raise PasarGuardConfigurationError(
                f"PasarGuard instance {instance.name!r} is missing configured "
                f"secret environment variable(s): {', '.join(configured)}"
            )
        raise PasarGuardConfigurationError(
            f"PasarGuard instance {instance.name!r} has no credential env mapping"
        )
    if api_key and bearer_token:
        raise PasarGuardConfigurationError(
            f"PasarGuard instance {instance.name!r} resolved both API key and bearer token"
        )

    return client_builder(
        base_url=instance.base_url,
        api_key=api_key,
        bearer_token=bearer_token,
        timeout_seconds=settings.pasarguard_timeout_seconds,
    )


class PasarGuardInstanceRouter:
    def __init__(
        self,
        *,
        settings: Settings,
        environment: Mapping[str, str] | None = None,
        client_builder: ClientBuilder = PasarGuardClient,
    ) -> None:
        self.settings = settings
        self.environment = os.environ if environment is None else environment
        self.client_builder = client_builder

    def _target_from_instance(
        self,
        instance: PasarGuardInstance,
    ) -> PasarGuardTarget:
        return PasarGuardTarget(
            instance_id=instance.id,
            name=instance.name,
            client=build_instance_client(
                self.settings,
                instance,
                environment=self.environment,
                client_builder=self.client_builder,
            ),
            reseller_role_id=(
                instance.reseller_role_id
                if instance.reseller_role_id is not None
                else self.settings.pasarguard_reseller_role_id
            ),
            reseller_role_name=(
                instance.reseller_role_name
                or self.settings.pasarguard_reseller_role_name
            ),
        )

    def _global_target(self) -> PasarGuardTarget:
        return PasarGuardTarget(
            instance_id=None,
            name="global",
            client=build_pasarguard_client(self.settings),
            reseller_role_id=self.settings.pasarguard_reseller_role_id,
            reseller_role_name=self.settings.pasarguard_reseller_role_name,
        )

    async def select_for_new_order(
        self,
        session: AsyncSession,
        *,
        routing_key: str,
    ) -> PasarGuardTarget:
        instances = list(
            (
                await session.scalars(
                    select(PasarGuardInstance)
                    .where(PasarGuardInstance.is_enabled.is_(True))
                    .order_by(PasarGuardInstance.name.asc())
                )
            ).all()
        )
        if not instances:
            return self._global_target()

        last_error: PasarGuardConfigurationError | None = None
        for instance in weighted_instance_order(
            instances,
            routing_key=routing_key,
        ):
            client: PasarGuardClient | None = None
            try:
                target = self._target_from_instance(instance)
                client = target.client
                healthy = await client.health()
            except PasarGuardConfigurationError as exc:
                last_error = exc
                healthy = False

            instance.last_health_at = datetime.now(UTC)
            instance.last_health_ok = healthy
            await session.flush()

            if healthy and client is not None:
                return target
            if client is not None:
                await client.close()

        try:
            fallback = self._global_target()
        except PasarGuardConfigurationError:
            if last_error is not None:
                raise last_error from None
            raise PasarGuardConfigurationError(
                "No healthy configured PasarGuard instance is available"
            ) from None

        if await fallback.client.health():
            return fallback
        await fallback.client.close()
        raise PasarGuardConfigurationError(
            "No healthy configured PasarGuard instance is available"
        )

    async def target_for_account(
        self,
        session: AsyncSession,
        *,
        account: PasarGuardAccount,
    ) -> PasarGuardTarget:
        if account.pasarguard_instance_id is None:
            return self._global_target()

        instance = await session.get(
            PasarGuardInstance,
            account.pasarguard_instance_id,
        )
        if instance is None:
            raise PasarGuardConfigurationError(
                "PasarGuard instance for account was not found"
            )
        return self._target_from_instance(instance)

    async def health_snapshot(
        self,
        session: AsyncSession,
    ) -> list[dict[str, object]]:
        instances = list(
            (
                await session.scalars(
                    select(PasarGuardInstance).order_by(
                        PasarGuardInstance.name.asc()
                    )
                )
            ).all()
        )
        rows: list[dict[str, object]] = []
        for instance in instances:
            client: PasarGuardClient | None = None
            error: str | None = None
            healthy = False
            try:
                target = self._target_from_instance(instance)
                client = target.client
                healthy = await client.health()
            except PasarGuardConfigurationError as exc:
                error = str(exc)

            instance.last_health_at = datetime.now(UTC)
            instance.last_health_ok = healthy
            rows.append(
                {
                    "id": str(instance.id),
                    "name": instance.name,
                    "base_url": instance.base_url,
                    "enabled": instance.is_enabled,
                    "weight": instance.weight,
                    "healthy": healthy,
                    "error": error,
                }
            )
            if client is not None:
                await client.close()

        await session.flush()
        return rows
