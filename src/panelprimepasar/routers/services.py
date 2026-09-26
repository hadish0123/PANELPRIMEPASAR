from html import escape
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.keyboards.customer import payment_receipt_keyboard
from panelprimepasar.keyboards.services import (
    lifecycle_plans_keyboard,
    subscription_actions_keyboard,
    subscription_picker_keyboard,
    subscriptions_keyboard,
)
from panelprimepasar.models import (
    Customer,
    Order,
    OrderKind,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from panelprimepasar.services.orders import list_active_plans
from panelprimepasar.services.payment_methods import list_enabled_payment_methods
from panelprimepasar.services.subscriptions import (
    create_lifecycle_order,
    get_customer_subscription,
    list_customer_subscriptions,
)

router = Router(name="customer_services")


class LifecycleForm(StatesGroup):
    choosing_plan = State()


def _format_money(amount: int, currency: str) -> str:
    labels = {"IRR": "ریال", "IRT": "تومان"}
    return f"{amount:,} {labels.get(currency.upper(), currency)}"


def _format_quota(quota_bytes: int) -> str:
    decimal_tb = 1_000_000_000_000
    decimal_gb = 1_000_000_000
    if quota_bytes % decimal_tb == 0:
        return f"{quota_bytes // decimal_tb} TB"
    if quota_bytes % decimal_gb == 0:
        return f"{quota_bytes // decimal_gb} GB"
    return f"{quota_bytes / decimal_gb:.2f} GB"


async def _customer_for_user(
    session: AsyncSession,
    telegram_user_id: int,
) -> Customer | None:
    return await session.scalar(
        select(Customer).where(Customer.telegram_user_id == telegram_user_id)
    )


async def _send_subscription_list(
    message: Message,
    session: AsyncSession,
    *,
    action: str | None = None,
) -> None:
    if message.from_user is None:
        return

    customer = await _customer_for_user(session, message.from_user.id)
    if customer is None:
        await message.answer("ابتدا /start را ارسال کنید.")
        return

    subscriptions = await list_customer_subscriptions(
        session,
        customer_id=customer.id,
    )
    if not subscriptions:
        await message.answer("هنوز سرویس فعالی برای این حساب ثبت نشده است.")
        return

    if action is None:
        await message.answer(
            "سرویس موردنظر را انتخاب کنید:",
            reply_markup=subscriptions_keyboard(subscriptions),
        )
        return

    await message.answer(
        "سرویسی که می‌خواهید تغییر دهید انتخاب کنید:",
        reply_markup=subscription_picker_keyboard(
            subscriptions,
            action=action,
        ),
    )


@router.message(F.text == "📦 سرویس‌های من")
async def my_services(message: Message, session: AsyncSession) -> None:
    await _send_subscription_list(message, session)


@router.message(F.text == "🔄 تمدید سرویس")
async def renew_service_entry(message: Message, session: AsyncSession) -> None:
    await _send_subscription_list(message, session, action=OrderKind.RENEWAL.value)


@router.message(F.text == "➕ افزایش حجم")
async def topup_service_entry(message: Message, session: AsyncSession) -> None:
    await _send_subscription_list(message, session, action=OrderKind.TOPUP.value)


@router.callback_query(F.data == "svc_list")
async def service_list_callback(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await _send_subscription_list(callback.message, session)


@router.callback_query(F.data.startswith("svc:"))
async def service_details(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    try:
        subscription_id = UUID(hex=(callback.data or "").removeprefix("svc:"))
    except ValueError:
        await callback.answer("شناسه سرویس معتبر نیست.", show_alert=True)
        return

    customer = await _customer_for_user(session, callback.from_user.id)
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    subscription = await get_customer_subscription(
        session,
        customer_id=customer.id,
        subscription_id=subscription_id,
    )
    if subscription is None:
        await callback.answer("سرویس پیدا نشد.", show_alert=True)
        return

    plan = await session.scalar(select(Plan).where(Plan.id == subscription.plan_id))
    expires = (
        subscription.expires_at.strftime("%Y-%m-%d")
        if subscription.expires_at is not None
        else "بدون محدودیت"
    )
    plan_name = escape(plan.name) if plan is not None else "پلن حذف‌شده"
    status_label = {
        SubscriptionStatus.ACTIVE.value: "فعال",
        SubscriptionStatus.EXPIRED.value: "منقضی",
        SubscriptionStatus.SUSPENDED.value: "معلق",
        SubscriptionStatus.CANCELED.value: "لغوشده",
    }.get(subscription.status, subscription.status)

    await callback.answer()
    await callback.message.answer(
        f"<b>{plan_name}</b>\n"
        f"شناسه سرویس: <code>{subscription.id}</code>\n"
        f"وضعیت: <b>{status_label}</b>\n"
        f"حجم ثبت‌شده: <b>{_format_quota(subscription.quota_bytes)}</b>\n"
        f"انقضا: <b>{expires}</b>",
        reply_markup=subscription_actions_keyboard(subscription.id),
    )


async def _start_lifecycle(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    *,
    subscription_id: UUID,
    kind: OrderKind,
) -> None:
    customer = await _customer_for_user(session, callback.from_user.id)
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    subscription = await get_customer_subscription(
        session,
        customer_id=customer.id,
        subscription_id=subscription_id,
    )
    if subscription is None:
        await callback.answer("سرویس پیدا نشد.", show_alert=True)
        return

    plans = await list_active_plans(session)
    if not plans:
        await callback.answer("پلن فعالی برای فروش وجود ندارد.", show_alert=True)
        return

    await state.clear()
    await state.update_data(
        subscription_id=str(subscription.id),
        order_kind=kind.value,
    )
    await state.set_state(LifecycleForm.choosing_plan)
    await callback.answer()
    if isinstance(callback.message, Message):
        title = "پلن تمدید" if kind == OrderKind.RENEWAL else "بسته افزایش حجم"
        await callback.message.answer(
            f"{title} را انتخاب کنید:",
            reply_markup=lifecycle_plans_keyboard(plans),
        )


@router.callback_query(F.data.startswith("svc_renew:"))
async def renew_service_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        subscription_id = UUID(
            hex=(callback.data or "").removeprefix("svc_renew:")
        )
    except ValueError:
        await callback.answer("شناسه سرویس معتبر نیست.", show_alert=True)
        return
    await _start_lifecycle(
        callback,
        state,
        session,
        subscription_id=subscription_id,
        kind=OrderKind.RENEWAL,
    )


@router.callback_query(F.data.startswith("svc_topup:"))
async def topup_service_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        subscription_id = UUID(
            hex=(callback.data or "").removeprefix("svc_topup:")
        )
    except ValueError:
        await callback.answer("شناسه سرویس معتبر نیست.", show_alert=True)
        return
    await _start_lifecycle(
        callback,
        state,
        session,
        subscription_id=subscription_id,
        kind=OrderKind.TOPUP,
    )


@router.callback_query(F.data.startswith("svcact:"))
async def service_action_picker(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = (callback.data or "").split(":")
    if len(data) != 3:
        await callback.answer("درخواست معتبر نیست.", show_alert=True)
        return

    _, raw_kind, raw_id = data
    try:
        kind = OrderKind(raw_kind)
        subscription_id = UUID(hex=raw_id)
    except (ValueError, TypeError):
        await callback.answer("درخواست معتبر نیست.", show_alert=True)
        return

    if kind not in {OrderKind.RENEWAL, OrderKind.TOPUP}:
        await callback.answer("نوع عملیات معتبر نیست.", show_alert=True)
        return

    await _start_lifecycle(
        callback,
        state,
        session,
        subscription_id=subscription_id,
        kind=kind,
    )


@router.callback_query(
    LifecycleForm.choosing_plan,
    F.data.startswith("lifeplan:"),
)
async def lifecycle_plan_selected(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    try:
        plan_id = UUID(hex=(callback.data or "").removeprefix("lifeplan:"))
    except ValueError:
        await callback.answer("شناسه پلن معتبر نیست.", show_alert=True)
        return

    data = await state.get_data()
    try:
        subscription_id = UUID(str(data["subscription_id"]))
        kind = OrderKind(str(data["order_kind"]))
    except (KeyError, ValueError):
        await state.clear()
        await callback.answer("فرآیند منقضی شده است.", show_alert=True)
        return

    customer = await _customer_for_user(session, callback.from_user.id)
    if customer is None:
        await state.clear()
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    subscription = await get_customer_subscription(
        session,
        customer_id=customer.id,
        subscription_id=subscription_id,
    )
    plan = await session.scalar(
        select(Plan).where(
            Plan.id == plan_id,
            Plan.is_active.is_(True),
        )
    )
    if subscription is None or plan is None:
        await state.clear()
        await callback.answer("سرویس یا پلن دیگر در دسترس نیست.", show_alert=True)
        return

    idempotency_key = (
        f"telegram:{callback.from_user.id}:message:{callback.message.message_id}:"
        f"{kind.value}:{subscription.id}:{plan.id}"
    )
    order, created = await create_lifecycle_order(
        session,
        customer=customer,
        subscription=subscription,
        plan=plan,
        kind=kind,
        idempotency_key=idempotency_key,
    )
    await state.clear()

    instructions = get_settings().manual_payment_instructions
    payment_text = (
        escape(instructions)
        if instructions
        else "اطلاعات پرداخت هنوز توسط مدیریت تنظیم نشده است."
    )
    action_text = "تمدید" if kind == OrderKind.RENEWAL else "افزایش حجم"

    await callback.answer(
        "سفارش ثبت شد." if created else "این سفارش قبلاً ثبت شده است."
    )
    payment_methods = await list_enabled_payment_methods(session)
    await callback.message.answer(
        f"سفارش {action_text} ثبت شد.\n"
        f"شماره سفارش: <code>{order.id}</code>\n"
        f"مبلغ: <b>{_format_money(order.price_amount, order.currency)}</b>\n\n"
        f"{payment_text}\n\n"
        "پس از پرداخت، رسید را ارسال کنید.",
        reply_markup=payment_receipt_keyboard(order.id, payment_methods),
    )


@router.callback_query(F.data == "life_cancel")
async def lifecycle_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("عملیات لغو شد.")


@router.message(F.text == "👤 حساب من")
async def profile(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    customer = await _customer_for_user(session, message.from_user.id)
    if customer is None:
        await message.answer("ابتدا /start را ارسال کنید.")
        return

    order_count = int(
        await session.scalar(
            select(func.count(Order.id)).where(Order.customer_id == customer.id)
        )
        or 0
    )
    active_count = int(
        await session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.customer_id == customer.id,
                Subscription.status == SubscriptionStatus.ACTIVE.value,
            )
        )
        or 0
    )

    username = (
        f"@{escape(customer.telegram_username)}"
        if customer.telegram_username
        else "ثبت نشده"
    )
    await message.answer(
        "<b>حساب کاربری</b>\n\n"
        f"Telegram ID: <code>{customer.telegram_user_id}</code>\n"
        f"Username: {username}\n"
        f"تعداد سفارش‌ها: <b>{order_count}</b>\n"
        f"سرویس فعال: <b>{active_count}</b>"
    )
