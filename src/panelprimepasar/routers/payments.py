from html import escape
from uuid import UUID

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    PaymentMethodKind,
)
from panelprimepasar.payments.base import PaymentProviderError
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.payment_methods import (
    PaymentMethodStateError,
    get_payment_method_by_slug,
    parse_public_config,
    start_external_payment,
)
from panelprimepasar.services.payments import PaymentStateError

router = Router(name="customer_payments")


async def _owned_order(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    order_id: UUID,
) -> tuple[Customer, Order] | None:
    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == telegram_user_id)
    )
    if customer is None:
        return None
    order = await session.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.customer_id == customer.id,
        )
    )
    if order is None:
        return None
    return customer, order


def _parse_method_callback(
    data: str | None,
    *,
    prefix: str,
) -> tuple[str, UUID] | None:
    raw = data or ""
    expected = f"{prefix}:"
    if not raw.startswith(expected):
        return None
    parts = raw.removeprefix(expected).split(":", maxsplit=1)
    if len(parts) != 2:
        return None
    slug, order_hex = parts
    try:
        order_id = UUID(hex=order_hex)
    except ValueError:
        return None
    return slug, order_id


def _format_card_number(value: str) -> str:
    compact = value.replace(" ", "").replace("-", "")
    return " ".join(
        compact[index : index + 4]
        for index in range(0, len(compact), 4)
    )


@router.callback_query(F.data.startswith("pmcard:"))
async def manual_card_payment(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    parsed = _parse_method_callback(callback.data, prefix="pmcard")
    if parsed is None:
        await callback.answer("اطلاعات روش پرداخت معتبر نیست.", show_alert=True)
        return
    slug, order_id = parsed

    owned = await _owned_order(
        session,
        telegram_user_id=callback.from_user.id,
        order_id=order_id,
    )
    if owned is None:
        await callback.answer("سفارش پیدا نشد.", show_alert=True)
        return
    _, order = owned
    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        await callback.answer("این سفارش دیگر در مرحله پرداخت نیست.", show_alert=True)
        return

    try:
        method = await get_payment_method_by_slug(
            session,
            slug=slug,
            enabled_only=True,
        )
        if method is None or method.kind != PaymentMethodKind.MANUAL_CARD.value:
            raise PaymentMethodStateError("روش کارت‌به‌کارت فعال نیست")
        config = parse_public_config(method)
    except PaymentMethodStateError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    card_number = config.get("card_number", "")
    card_holder = config.get("card_holder", "")
    bank_name = config.get("bank_name", "")
    iban = config.get("iban", "")
    instructions = config.get("instructions", "")

    lines = [
        f"<b>{escape(method.display_name)}</b>",
        "",
        f"شماره کارت: <code>{escape(_format_card_number(card_number))}</code>",
        f"به نام: <b>{escape(card_holder)}</b>",
    ]
    if bank_name:
        lines.append(f"بانک: <b>{escape(bank_name)}</b>")
    if iban:
        lines.append(f"شبا: <code>{escape(iban)}</code>")
    if instructions:
        lines.extend(["", escape(instructions)])
    lines.extend(
        [
            "",
            f"مبلغ سفارش: <b>{order.price_amount:,} {escape(order.currency)}</b>",
            "بعد از انتقال وجه، رسید را ارسال کنید.",
        ]
    )

    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📎 ارسال رسید",
                            callback_data=f"receipt:{order.id}",
                        )
                    ]
                ]
            ),
        )


@router.callback_query(F.data.startswith("pm:"))
async def online_gateway_payment(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    parsed = _parse_method_callback(callback.data, prefix="pm")
    if parsed is None:
        await callback.answer("اطلاعات درگاه معتبر نیست.", show_alert=True)
        return
    slug, order_id = parsed

    owned = await _owned_order(
        session,
        telegram_user_id=callback.from_user.id,
        order_id=order_id,
    )
    if owned is None:
        await callback.answer("سفارش پیدا نشد.", show_alert=True)
        return
    customer, order = owned
    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        await callback.answer("این سفارش دیگر در مرحله پرداخت نیست.", show_alert=True)
        return

    method = await get_payment_method_by_slug(
        session,
        slug=slug,
        enabled_only=True,
    )
    if method is None or method.kind == PaymentMethodKind.MANUAL_CARD.value:
        await callback.answer("درگاه فعال نیست.", show_alert=True)
        return

    try:
        payment, intent = await start_external_payment(
            session,
            settings=get_settings(),
            order=order,
            method=method,
        )
        await record_audit_event(
            session,
            actor_type="customer",
            actor_id=str(customer.telegram_user_id),
            action="payment.external_started",
            entity_type="payment",
            entity_id=str(payment.id),
            correlation_id=str(order.id),
            metadata={
                "provider": method.kind,
                "payment_method_id": str(method.id),
                "order_id": str(order.id),
            },
        )
        await session.commit()
    except (PaymentMethodStateError, PaymentProviderError, PaymentStateError) as exc:
        await session.rollback()
        await callback.answer("اتصال به درگاه انجام نشد.", show_alert=True)
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "در ایجاد پرداخت بانکی خطایی رخ داد. "
                "روش دیگری را انتخاب کنید یا کمی بعد دوباره تلاش کنید.\n"
                f"<code>{escape(str(exc))}</code>"
            )
        return

    await callback.answer()
    if not intent.payment_url:
        if isinstance(callback.message, Message):
            await callback.message.answer("لینک پرداخت از درگاه دریافت نشد.")
        return

    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"برای پرداخت سفارش <code>{order.id}</code> از "
            f"<b>{escape(method.display_name)}</b> استفاده کنید.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"🏦 ورود به {method.display_name}",
                            url=intent.payment_url,
                        )
                    ]
                ]
            ),
        )
