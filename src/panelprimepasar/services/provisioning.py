import random
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.integrations.pasarguard import (
    PasarGuardAdmin,
    PasarGuardError,
    PasarGuardRole,
)
from panelprimepasar.models import (
    Customer,
    Order,
    OrderKind,
    OrderStatus,
    PasarGuardAccount,
    ProvisioningJob,
    ProvisioningStatus,
    Subscription,
    SubscriptionStatus,
)


class ProvisioningStateError(RuntimeError):
    """Raised when an order cannot enter provisioning from its current state."""


class ProvisioningClient(Protocol):
    async def resolve_reseller_role(
        self,
        *,
        role_id: int | None,
        role_name: str | None,
    ) -> PasarGuardRole: ...

    async def ensure_admin(
        self,
        *,
        username: str,
        password: str,
        role_id: int,
        data_limit: int | None,
        note: str | None = None,
    ) -> PasarGuardAdmin: ...


@dataclass(frozen=True, slots=True)
class ProvisionedCredentials:
    username: str
    password: str
    admin_id: int
    role_id: int
    role_name: str


@dataclass(frozen=True, slots=True)
class ProvisioningOutcome:
    success: bool
    credentials: ProvisionedCredentials | None = None
    already_provisioned: bool = False
    error_code: str | None = None
    error_message: str | None = None


def build_reseller_username(*, telegram_user_id: int, order_id: UUID) -> str:
    username = f"r{telegram_user_id}_{order_id.hex[:8]}"
    if len(username) > 34:
        raise ValueError("Generated PasarGuard admin username exceeds 34 characters")
    return username


def generate_reseller_password(*, username: str, length: int = 24) -> str:
    if length < 12:
        raise ValueError("Password length must be at least 12")
    if length > 72:
        raise ValueError("Password length must be at most 72 ASCII characters")

    special = "!@#$%^&*()-_=+"
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(string.digits),
        secrets.choice(special),
    ]
    alphabet = string.ascii_letters + string.digits + special
    required.extend(secrets.choice(alphabet) for _ in range(length - len(required)))

    random.SystemRandom().shuffle(required)
    password = "".join(required)

    if username.casefold() in password.casefold():
        return generate_reseller_password(username=username, length=length)
    return password


class ProvisioningService:
    def __init__(
        self,
        *,
        client: ProvisioningClient,
        reseller_role_id: int | None,
        reseller_role_name: str | None,
        pasarguard_instance_id: UUID | None = None,
    ) -> None:
        self.client = client
        self.reseller_role_id = reseller_role_id
        self.reseller_role_name = reseller_role_name
        self.pasarguard_instance_id = pasarguard_instance_id

    async def _get_job(self, session: AsyncSession, order_id: UUID) -> ProvisioningJob:
        job = await session.scalar(
            select(ProvisioningJob).where(ProvisioningJob.order_id == order_id)
        )
        if job is None:
            job = ProvisioningJob(
                order_id=order_id,
                status=ProvisioningStatus.PENDING,
                attempts=0,
            )
            session.add(job)
            await session.flush()
        return job

    async def _ensure_subscription(
        self,
        session: AsyncSession,
        *,
        order: Order,
        account: PasarGuardAccount,
    ) -> Subscription:
        subscription = await session.scalar(
            select(Subscription).where(Subscription.source_order_id == order.id)
        )
        if subscription is not None:
            return subscription

        starts_at = datetime.now(UTC)
        subscription = Subscription(
            customer_id=order.customer_id,
            plan_id=order.plan_id,
            pasar_guard_account_id=account.id,
            source_order_id=order.id,
            status=SubscriptionStatus.ACTIVE.value,
            quota_bytes=order.quota_bytes,
            starts_at=starts_at,
            expires_at=None,
            auto_renew=False,
        )
        session.add(subscription)
        await session.flush()
        return subscription

    async def reissue_credentials(
        self,
        session: AsyncSession,
        *,
        order_id: UUID,
    ) -> ProvisioningOutcome:
        order = await session.scalar(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        if order is None:
            raise ProvisioningStateError("Order not found")
        if order.kind != OrderKind.NEW:
            raise ProvisioningStateError(
                f"Order kind {order.kind.value!r} must use subscription lifecycle provisioning"
            )

        customer = await session.scalar(
            select(Customer).where(Customer.id == order.customer_id)
        )
        account = await session.scalar(
            select(PasarGuardAccount).where(PasarGuardAccount.order_id == order.id)
        )
        if customer is None or account is None:
            raise ProvisioningStateError("Provisioned account not found")

        role = await self.client.resolve_reseller_role(
            role_id=self.reseller_role_id,
            role_name=self.reseller_role_name,
        )
        password = generate_reseller_password(username=account.username)

        try:
            admin = await self.client.ensure_admin(
                username=account.username,
                password=password,
                role_id=role.id,
                data_limit=order.quota_bytes,
                note=f"PANELPRIMEPASAR order {order.id}",
            )
            if admin.id is None:
                raise PasarGuardError(
                    "PasarGuard credential rotation response did not include admin ID"
                )
        except PasarGuardError as exc:
            return ProvisioningOutcome(
                success=False,
                error_code=type(exc).__name__,
                error_message=str(exc)[:1000],
            )

        account.pasarguard_instance_id = self.pasarguard_instance_id
        account.pasarguard_admin_id = admin.id
        account.role_id = role.id
        account.role_name = role.name
        account.quota_bytes = order.quota_bytes
        account.is_active = True
        order.status = OrderStatus.COMPLETED
        await session.flush()

        return ProvisioningOutcome(
            success=True,
            already_provisioned=True,
            credentials=ProvisionedCredentials(
                username=account.username,
                password=password,
                admin_id=admin.id,
                role_id=role.id,
                role_name=role.name,
            ),
        )

    async def provision_paid_order(
        self,
        session: AsyncSession,
        *,
        order_id: UUID,
    ) -> ProvisioningOutcome:
        order = await session.scalar(
            select(Order).where(Order.id == order_id).with_for_update()
        )
        if order is None:
            raise ProvisioningStateError("Order not found")
        if order.kind != OrderKind.NEW:
            raise ProvisioningStateError(
                f"Order kind {order.kind.value!r} must use subscription lifecycle provisioning"
            )

        customer = await session.scalar(
            select(Customer).where(Customer.id == order.customer_id)
        )
        if customer is None:
            raise ProvisioningStateError("Order customer not found")

        existing_account = await session.scalar(
            select(PasarGuardAccount).where(PasarGuardAccount.order_id == order.id)
        )
        if (
            existing_account is not None
            and existing_account.pasarguard_admin_id is not None
        ):
            await self._ensure_subscription(
                session,
                order=order,
                account=existing_account,
            )
            order.status = OrderStatus.COMPLETED
            job = await self._get_job(session, order.id)
            job.status = ProvisioningStatus.SUCCEEDED
            job.completed_at = datetime.now(UTC)
            job.last_error_code = None
            job.last_error_message = None
            await session.flush()
            return ProvisioningOutcome(
                success=True,
                already_provisioned=True,
            )

        allowed_states = {
            OrderStatus.PAID,
            OrderStatus.PROVISIONING,
            OrderStatus.FAILED,
        }
        if order.status not in allowed_states:
            raise ProvisioningStateError(
                f"Order status {order.status.value!r} cannot be provisioned"
            )

        job = await self._get_job(session, order.id)
        job.status = ProvisioningStatus.RUNNING
        job.attempts += 1
        job.last_error_code = None
        job.last_error_message = None
        order.status = OrderStatus.PROVISIONING
        await session.flush()

        username = build_reseller_username(
            telegram_user_id=customer.telegram_user_id,
            order_id=order.id,
        )
        password = generate_reseller_password(username=username)

        try:
            role = await self.client.resolve_reseller_role(
                role_id=self.reseller_role_id,
                role_name=self.reseller_role_name,
            )
            admin = await self.client.ensure_admin(
                username=username,
                password=password,
                role_id=role.id,
                data_limit=order.quota_bytes,
                note=f"PANELPRIMEPASAR order {order.id}",
            )
            if admin.id is None:
                raise PasarGuardError("PasarGuard create/update response did not include admin ID")
        except PasarGuardError as exc:
            job.status = ProvisioningStatus.FAILED
            job.last_error_code = type(exc).__name__
            job.last_error_message = str(exc)[:1000]
            order.status = OrderStatus.FAILED
            await session.flush()
            return ProvisioningOutcome(
                success=False,
                error_code=job.last_error_code,
                error_message=job.last_error_message,
            )

        account = PasarGuardAccount(
            customer_id=customer.id,
            order_id=order.id,
            pasarguard_instance_id=self.pasarguard_instance_id,
            pasarguard_admin_id=admin.id,
            username=username,
            role_id=role.id,
            role_name=role.name,
            quota_bytes=order.quota_bytes,
            is_active=True,
        )
        session.add(account)
        await session.flush()
        await self._ensure_subscription(
            session,
            order=order,
            account=account,
        )

        order.status = OrderStatus.COMPLETED
        job.status = ProvisioningStatus.SUCCEEDED
        job.completed_at = datetime.now(UTC)
        job.last_error_code = None
        job.last_error_message = None
        await session.flush()

        return ProvisioningOutcome(
            success=True,
            credentials=ProvisionedCredentials(
                username=username,
                password=password,
                admin_id=admin.id,
                role_id=role.id,
                role_name=role.name,
            ),
        )
