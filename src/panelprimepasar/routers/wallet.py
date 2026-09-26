from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.integrations.pasarguard import PasarGuardError
from panelprimepasar.models import Customer, OrderKind
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.fulfillment import fulfill_paid_order
from panelprimepasar.services.panel_urls import resolve_order_panel_url
from panelprimepasar.services.provisioning import ProvisioningStateError
from panelprimepasar.services.subscriptions import SubscriptionStateError
from panelprimepasar.services.wallets import (
    WalletStateError,
    get_or_create_wallet,
    list_wallet_transactions,
    pay_order_with_wallet,
)

router = Router(name="customer_wallet")


async def _customer(
    session: AsyncSession,
    *,
    telegram_user_id: int,
) -> Customer | None:
    return await session.scalar(
        select(Customer).where(Customer.telegram_user_id == telegram_user_id)
    )


def _transaction_label(kind: str) -> str:
    labels = {
        "credit": "واریز",
        "debit": "برداشت",
        "refund": "بازگشت وجه",
        "commission": "کمیسیون",
        "adjustment": "اصلاح",
    }
    return labels.get(kind, kind)


@router.message(F.text == "💰 کیف پول")
async def wallet_home(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    customer = await _customer(
        session,
        telegram_user_id=message.from_user.id,
    )
    if customer is None:
        await message.answer("ابتدا /start را ارسال کنید.")
        return

    wallet = await get_or_create_wallet(
        session,
        customer_id=customer.id,
        currency="IRT",
    )
    transactions = await list_wallet_transactions(
        session,
        wallet_id=wallet.id,
        limit=5,
    )

    rows = []
    for transaction in transactions:
        sign = "-" if transaction.kind == "debit" else "+"
        rows.append(
            f"• {_transaction_label(transaction.kind)}: "
            f"<b>{sign}{transaction.amount:,} {escape(transaction.currency)}</b>"
        )

    await message.answer(
        "<b>کیف پول</b>\n\n"
        f"موجودی: <b>{wallet.balance:,} {escape(wallet.currency)}</b>\n\n"
        + ("<b>تراکنش‌های اخیر:</b>\n" + "\n".join(rows) if rows else "هنوز تراکنشی ثبت نشده است.")
    )


@router.callback_query(F.data.startswith("wallet_pay:"))
async def wallet_pay(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
) -> None:
    try:
        order_id = UUID((callback.data or "").removeprefix("wallet_pay:"))
    except ValueError:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    customer = await _customer(
        session,
        telegram_user_id=callback.from_user.id,
    )
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    try:
        payment = await pay_order_with_wallet(
            session,
            customer_id=customer.id,
            order_id=order_id,
        )
        await record_audit_event(
            session,
            actor_type="customer",
            actor_id=str(customer.telegram_user_id),
            action="payment.wallet_verified",
            entity_type="order",
            entity_id=str(order_id),
            correlation_id=str(order_id),
            metadata={
                "payment_id": str(payment.id),
                "amount": payment.amount,
                "currency": payment.currency,
            },
        )
        await session.commit()
    except WalletStateError as exc:
        await session.rollback()
        await callback.answer(str(exc), show_alert=True)
        return

    await callback.answer("پرداخت از کیف پول انجام شد.")

    try:
        outcome = await fulfill_paid_order(
            session,
            settings=get_settings(),
            order_id=order_id,
        )
        await record_audit_event(
            session,
            actor_type="system",
            actor_id=None,
            action=(
                "order.auto_fulfillment_succeeded"
                if outcome.success
                else "order.auto_fulfillment_failed"
            ),
            entity_type="order",
            entity_id=str(order_id),
            correlation_id=str(order_id),
            metadata={
                "order_kind": outcome.order_kind.value,
                "error_code": outcome.error_code,
            },
        )
        await session.commit()
    except (PasarGuardError, ProvisioningStateError, SubscriptionStateError) as exc:
        await session.rollback()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "پرداخت ثبت شد اما اجرای خودکار سفارش با خطا مواجه شد. "
                "مدیریت می‌تواند عملیات را دوباره اجرا کند.\n"
                f"<code>{escape(str(exc))}</code>"
            )
        return

    if not outcome.success:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "پرداخت موفق بود اما اجرای سرویس کامل نشد. "
                "سفارش برای تلاش مجدد مدیریت باقی مانده است."
            )
        return

    if outcome.order_kind == OrderKind.NEW:
        credentials = outcome.credentials
        if credentials is None:
            if isinstance(callback.message, Message):
                await callback.message.answer(
                    "✅ پرداخت و ساخت پنل تکمیل شده است. "
                    "برای دریافت رمز جدید در صورت نیاز با پشتیبانی تماس بگیرید."
                )
            return

        settings = get_settings()
        panel_url = await resolve_order_panel_url(
            session,
            settings=settings,
            order_id=order_id,
        )
        try:
            await bot.send_message(
                customer.telegram_user_id,
                "<b>پنل نمایندگی شما آماده است.</b>\n\n"
                f"آدرس پنل: <code>{escape(panel_url)}</code>\n"
                f"نام کاربری: <code>{escape(credentials.username)}</code>\n"
                f"رمز عبور: <code>{escape(credentials.password)}</code>\n\n"
                "رمز را در محل امن نگه‌داری کنید.",
            )
        except TelegramAPIError:
            if isinstance(callback.message, Message):
                await callback.message.answer(
                    "پنل ساخته شد اما ارسال مشخصات ناموفق بود؛ "
                    "از پشتیبانی درخواست صدور مجدد رمز کنید."
                )
            return
    elif isinstance(callback.message, Message):
        action = "تمدید" if outcome.order_kind == OrderKind.RENEWAL else "افزایش حجم"
        await callback.message.answer(f"✅ {action} سرویس با موفقیت انجام شد.")
