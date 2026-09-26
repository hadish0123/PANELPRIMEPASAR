from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.integrations.pasarguard import PasarGuardError
from panelprimepasar.keyboards.customer import payment_receipt_keyboard
from panelprimepasar.models import Customer, Order, OrderKind, OrderStatus
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.discounts import (
    DiscountStateError,
    reserve_discount_for_order,
)
from panelprimepasar.services.fulfillment import fulfill_paid_order
from panelprimepasar.services.payment_methods import list_enabled_payment_methods
from panelprimepasar.services.payments import PaymentStateError, settle_zero_price_order
from panelprimepasar.services.provisioning import ProvisioningStateError
from panelprimepasar.services.subscriptions import SubscriptionStateError

router = Router(name="customer_discounts")


class DiscountForm(StatesGroup):
    waiting_code = State()


async def _customer_order(
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


async def _deliver_free_order(
    *,
    message: Message,
    bot: Bot,
    session: AsyncSession,
    customer: Customer,
    order: Order,
) -> None:
    try:
        outcome = await fulfill_paid_order(
            session,
            settings=get_settings(),
            order_id=order.id,
        )
        await record_audit_event(
            session,
            actor_type="system",
            actor_id=None,
            action=(
                "order.discount_fulfillment_succeeded"
                if outcome.success
                else "order.discount_fulfillment_failed"
            ),
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(order.id),
            metadata={
                "order_kind": outcome.order_kind.value,
                "error_code": outcome.error_code,
            },
        )
        await session.commit()
    except (PasarGuardError, ProvisioningStateError, SubscriptionStateError) as exc:
        await session.rollback()
        await message.answer(
            "کد تخفیف ثبت و سفارش پرداخت‌شده محسوب شد، "
            "اما اجرای خودکار سرویس با خطا مواجه شد.\n"
            f"<code>{escape(str(exc))}</code>"
        )
        return

    if not outcome.success:
        await message.answer(
            "کد تخفیف ثبت شد اما اجرای سرویس کامل نشد. "
            "مدیریت می‌تواند عملیات را دوباره اجرا کند."
        )
        return

    if outcome.order_kind != OrderKind.NEW:
        action = "تمدید" if outcome.order_kind == OrderKind.RENEWAL else "افزایش حجم"
        await message.answer(f"✅ {action} سرویس با موفقیت انجام شد.")
        return

    credentials = outcome.credentials
    if credentials is None:
        await message.answer("✅ سفارش بدون نیاز به پرداخت تکمیل شد.")
        return

    settings = get_settings()
    try:
        await bot.send_message(
            customer.telegram_user_id,
            "<b>پنل نمایندگی شما آماده است.</b>\n\n"
            f"آدرس پنل: <code>{escape(str(settings.pasarguard_base_url).rstrip('/'))}</code>\n"
            f"نام کاربری: <code>{escape(credentials.username)}</code>\n"
            f"رمز عبور: <code>{escape(credentials.password)}</code>\n\n"
            "رمز را در محل امن نگه‌داری کنید.",
        )
    except TelegramAPIError:
        await message.answer(
            "پنل ساخته شد اما ارسال مشخصات ناموفق بود؛ "
            "از پشتیبانی درخواست صدور مجدد رمز کنید."
        )


@router.callback_query(F.data.startswith("discount:"))
async def discount_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        order_id = UUID((callback.data or "").removeprefix("discount:"))
    except ValueError:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    result = await _customer_order(
        session,
        telegram_user_id=callback.from_user.id,
        order_id=order_id,
    )
    if result is None:
        await callback.answer("سفارش پیدا نشد.", show_alert=True)
        return
    _, order = result
    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        await callback.answer("این سفارش دیگر قابل تخفیف نیست.", show_alert=True)
        return
    if order.discount_code_id is not None:
        await callback.answer("برای این سفارش قبلاً کد تخفیف ثبت شده است.", show_alert=True)
        return

    await state.clear()
    await state.update_data(order_id=str(order.id))
    await state.set_state(DiscountForm.waiting_code)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("کد تخفیف را ارسال کنید.")


@router.message(DiscountForm.waiting_code)
async def discount_code_received(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    data = await state.get_data()
    try:
        order_id = UUID(str(data["order_id"]))
    except (KeyError, ValueError):
        await state.clear()
        await message.answer("فرآیند کد تخفیف منقضی شده است.")
        return

    result = await _customer_order(
        session,
        telegram_user_id=message.from_user.id,
        order_id=order_id,
    )
    if result is None:
        await state.clear()
        await message.answer("سفارش پیدا نشد.")
        return
    customer, order = result

    try:
        redemption = await reserve_discount_for_order(
            session,
            customer_id=customer.id,
            order_id=order.id,
            raw_code=message.text or "",
        )
        await record_audit_event(
            session,
            actor_type="customer",
            actor_id=str(customer.telegram_user_id),
            action="discount.reserved",
            entity_type="order",
            entity_id=str(order.id),
            correlation_id=str(redemption.id),
            metadata={
                "discount_code_id": str(redemption.discount_code_id),
                "discount_amount": redemption.amount,
            },
        )

        zero_price = order.price_amount == 0
        if zero_price:
            payment = await settle_zero_price_order(
                session,
                order_id=order.id,
            )
            await record_audit_event(
                session,
                actor_type="system",
                actor_id=None,
                action="payment.zero_price_verified",
                entity_type="order",
                entity_id=str(order.id),
                correlation_id=str(order.id),
                metadata={"payment_id": str(payment.id)},
            )
        await session.commit()
    except (DiscountStateError, PaymentStateError) as exc:
        await session.rollback()
        await message.answer(escape(str(exc)))
        return

    await state.clear()
    original_price = order.price_amount + redemption.amount
    await message.answer(
        "✅ کد تخفیف اعمال شد.\n"
        f"قیمت قبلی: <s>{original_price:,} {escape(order.currency)}</s>\n"
        f"تخفیف: <b>{redemption.amount:,} {escape(order.currency)}</b>\n"
        f"مبلغ نهایی: <b>{order.price_amount:,} {escape(order.currency)}</b>"
    )

    if zero_price:
        await _deliver_free_order(
            message=message,
            bot=bot,
            session=session,
            customer=customer,
            order=order,
        )
        return

    await message.answer(
        "روش پرداخت را انتخاب کنید یا رسید پرداخت را ارسال کنید.",
        reply_markup=payment_receipt_keyboard(order.id, payment_methods),
    )
