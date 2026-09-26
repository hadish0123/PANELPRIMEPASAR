import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import String, cast, exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from panelprimepasar.config import Settings
from panelprimepasar.integrations.factory import build_pasarguard_client
from panelprimepasar.integrations.pasarguard import (
    PasarGuardAdmin,
    PasarGuardConfigurationError,
    PasarGuardError,
)
from panelprimepasar.models import (
    AuditEvent,
    Customer,
    PasarGuardAccount,
    Subscription,
    SubscriptionStatus,
)
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.discounts import release_stale_discount_reservations


class MaintenanceClient(Protocol):
    async def modify_admin_by_id(
        self,
        admin_id: int,
        *,
        password: str | None = None,
        role_id: int | None = None,
        data_limit: int | None = None,
        status: str | None = None,
        note: str | None = None,
    ) -> PasarGuardAdmin: ...


@dataclass(frozen=True, slots=True)
class ExpiryResult:
    subscription_id: UUID
    telegram_user_id: int | None
    success: bool
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ExpiryWarning:
    subscription_id: UUID
    telegram_user_id: int
    expires_at: datetime


async def expire_due_subscriptions(
    session: AsyncSession,
    *,
    client: MaintenanceClient,
    now: datetime | None = None,
    limit: int = 100,
) -> list[ExpiryResult]:
    current = now or datetime.now(UTC)
    subscriptions = list(
        (
            await session.scalars(
                select(Subscription)
                .where(
                    Subscription.status == SubscriptionStatus.ACTIVE.value,
                    Subscription.expires_at.is_not(None),
                    Subscription.expires_at <= current,
                )
                .order_by(Subscription.expires_at.asc(), Subscription.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )

    results: list[ExpiryResult] = []
    for subscription in subscriptions:
        account = await session.scalar(
            select(PasarGuardAccount)
            .where(PasarGuardAccount.id == subscription.pasar_guard_account_id)
            .with_for_update()
        )
        customer = await session.get(Customer, subscription.customer_id)
        telegram_user_id = (
            customer.telegram_user_id if customer is not None else None
        )

        if account is None or account.pasarguard_admin_id is None:
            await record_audit_event(
                session,
                actor_type="system",
                actor_id=None,
                action="subscription.expiry_failed",
                entity_type="subscription",
                entity_id=str(subscription.id),
                correlation_id=str(subscription.id),
                metadata={"error_code": "PasarGuardAccountMissing"},
            )
            results.append(
                ExpiryResult(
                    subscription_id=subscription.id,
                    telegram_user_id=telegram_user_id,
                    success=False,
                    error_code="PasarGuardAccountMissing",
                    error_message="Provisioned PasarGuard account not found",
                )
            )
            continue

        try:
            await client.modify_admin_by_id(
                account.pasarguard_admin_id,
                status="disabled",
                note=f"PANELPRIMEPASAR expired subscription {subscription.id}",
            )
        except PasarGuardError as exc:
            await record_audit_event(
                session,
                actor_type="system",
                actor_id=None,
                action="subscription.expiry_failed",
                entity_type="subscription",
                entity_id=str(subscription.id),
                correlation_id=str(subscription.id),
                metadata={
                    "error_code": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
            )
            results.append(
                ExpiryResult(
                    subscription_id=subscription.id,
                    telegram_user_id=telegram_user_id,
                    success=False,
                    error_code=type(exc).__name__,
                    error_message=str(exc)[:1000],
                )
            )
            continue

        subscription.status = SubscriptionStatus.EXPIRED.value
        account.is_active = False
        await record_audit_event(
            session,
            actor_type="system",
            actor_id=None,
            action="subscription.expired",
            entity_type="subscription",
            entity_id=str(subscription.id),
            correlation_id=str(subscription.id),
        )
        results.append(
            ExpiryResult(
                subscription_id=subscription.id,
                telegram_user_id=telegram_user_id,
                success=True,
            )
        )

    await session.flush()
    return results


async def find_expiry_warnings(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    warning_hours: int = 72,
    limit: int = 100,
) -> list[ExpiryWarning]:
    current = now or datetime.now(UTC)
    warning_until = current + timedelta(hours=warning_hours)
    already_warned = exists(
        select(AuditEvent.id).where(
            AuditEvent.action == "subscription.expiry_warning_sent",
            AuditEvent.entity_type == "subscription",
            AuditEvent.entity_id == cast(Subscription.id, String),
        )
    )

    rows = await session.scalars(
        select(Subscription)
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE.value,
            Subscription.expires_at.is_not(None),
            Subscription.expires_at > current,
            Subscription.expires_at <= warning_until,
            ~already_warned,
        )
        .order_by(Subscription.expires_at.asc(), Subscription.id.asc())
        .limit(limit)
    )

    warnings: list[ExpiryWarning] = []
    for subscription in rows.all():
        customer = await session.get(Customer, subscription.customer_id)
        if customer is None or subscription.expires_at is None:
            continue
        warnings.append(
            ExpiryWarning(
                subscription_id=subscription.id,
                telegram_user_id=customer.telegram_user_id,
                expires_at=subscription.expires_at,
            )
        )
    return warnings


async def _notify_expired(bot: Bot, result: ExpiryResult) -> None:
    if result.telegram_user_id is None or not result.success:
        return
    try:
        await bot.send_message(
            result.telegram_user_id,
            "⛔ سرویس شما منقضی شده است. برای فعال‌سازی مجدد از بخش «تمدید سرویس» استفاده کنید.",
        )
    except TelegramAPIError:
        return


async def _notify_warning(
    session: AsyncSession,
    *,
    bot: Bot,
    warning: ExpiryWarning,
) -> None:
    try:
        await bot.send_message(
            warning.telegram_user_id,
            "⏳ سرویس شما به زمان انقضا نزدیک شده است.\n"
            f"تاریخ انقضا: <b>{warning.expires_at:%Y-%m-%d %H:%M UTC}</b>\n"
            "برای جلوگیری از قطع سرویس، از بخش «تمدید سرویس» اقدام کنید.",
        )
    except TelegramAPIError:
        return

    await record_audit_event(
        session,
        actor_type="system",
        actor_id=None,
        action="subscription.expiry_warning_sent",
        entity_type="subscription",
        entity_id=str(warning.subscription_id),
        correlation_id=str(warning.subscription_id),
        metadata={"telegram_user_id": warning.telegram_user_id},
    )


async def run_subscription_maintenance_once(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    bot: Bot | None,
) -> None:
    async with session_factory() as session:
        released_discounts = await release_stale_discount_reservations(
            session,
            max_age_hours=settings.discount_reservation_max_age_hours,
        )
        if released_discounts:
            await record_audit_event(
                session,
                actor_type="system",
                actor_id=None,
                action="discount.stale_reservations_released",
                entity_type="discount_redemption",
                entity_id=None,
                metadata={"count": released_discounts},
            )
        await session.commit()

    try:
        client = build_pasarguard_client(settings)
    except PasarGuardConfigurationError:
        return

    try:
        async with session_factory() as session:
            warnings = await find_expiry_warnings(
                session,
                warning_hours=settings.subscription_expiry_warning_hours,
            )
            if bot is not None:
                for warning in warnings:
                    await _notify_warning(session, bot=bot, warning=warning)

            results = await expire_due_subscriptions(
                session,
                client=client,
            )
            await session.commit()

        if bot is not None:
            for result in results:
                await _notify_expired(bot, result)
    finally:
        await client.close()


async def subscription_maintenance_loop(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    bot: Bot | None,
) -> None:
    while True:
        try:
            await run_subscription_maintenance_once(
                session_factory=session_factory,
                settings=settings,
                bot=bot,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # The next cycle retries. Individual operations are audit logged.
            pass

        await asyncio.sleep(settings.subscription_maintenance_interval_seconds)
