from html import escape
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.keyboards.customer import (
    main_menu,
    plan_actions_keyboard,
    plans_keyboard,
)
from panelprimepasar.models import Customer, OrderStatus
from panelprimepasar.services.orders import (
    checkout_idempotency_key,
    get_active_plan,
    get_or_create_checkout_order,
    list_active_plans,
    list_customer_orders,
    upsert_customer,
)

router = Router(name="customer")


def format_money(amount: int, currency: str) -> str:
    labels = {"IRR": "ریال", "IRT": "تومان"}
    return f"{amount:,} {labels.get(currency.upper(), currency)}"


def format_quota(quota_bytes: int) -> str:
    decimal_tb = 1_000_000_000_000
    decimal_gb = 1_000_000_000
    binary_tib = 1_099_511_627_776
    binary_gib = 1_073_741_824

    if quota_bytes % decimal_tb == 0:
        return f"{quota_bytes // decimal_tb} TB"
    if quota_bytes % binary_tib == 0:
        return f"{quota_bytes // binary_tib} TiB"
    if quota_bytes % decimal_gb == 0:
        return f"{quota_bytes // decimal_gb} GB"
    if quota_bytes % binary_gib == 0:
        return f"{quota_bytes // binary_gib} GiB"
    return f"{quota_bytes / decimal_gb:.2f} GB"


def order_status_label(status: OrderStatus) -> str:
    labels = {
        OrderStatus.PENDING: "در انتظار",
        OrderStatus.AWAITING_PAYMENT: "در انتظار پرداخت",
        OrderStatus.PAID: "پرداخت‌شده",
        OrderStatus.PROVISIONING: "در حال ساخت پنل",
        OrderStatus.COMPLETED: "تکمیل‌شده",
        OrderStatus.FAILED: "ناموفق",
        OrderStatus.CANCELED: "لغوشده",
    }
    return labels[status]


async def ensure_customer(message: Message, session: AsyncSession) -> Customer | None:
    user = message.from_user
    if user is None:
        return None
    return await upsert_customer(
        session,
        telegram_user_id=user.id,
        telegram_username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )


async def send_catalog(message: Message, session: AsyncSession) -> None:
    plans = await list_active_plans(session)
    if not plans:
        await message.answer("در حال حاضر پلن فعالی برای فروش ثبت نشده است.")
        return

    await message.answer(
        "پلن موردنظر را انتخاب کنید:",
        reply_markup=plans_keyboard(plans),
    )


@router.message(CommandStart())
async def start_handler(message: Message, session: AsyncSession) -> None:
    await ensure_customer(message, session)
    await message.answer(
        "به سامانه فروش پنل پاسارگارد خوش آمدید.",
        reply_markup=main_menu(),
    )


@router.message(F.text == "🛒 خرید پنل")
async def catalog_handler(message: Message, session: AsyncSession) -> None:
    await ensure_customer(message, session)
    await send_catalog(message, session)


@router.callback_query(F.data == "catalog")
async def catalog_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await send_catalog(callback.message, session)


@router.callback_query(F.data.startswith("plan:"))
async def plan_details(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    data = callback.data or ""
    try:
        plan_id = UUID(data.removeprefix("plan:"))
    except ValueError:
        await callback.message.answer("شناسه پلن معتبر نیست.")
        return

    plan = await get_active_plan(session, plan_id)
    if plan is None:
        await callback.message.answer("این پلن دیگر فعال نیست.")
        return

    validity = (
        f"{plan.validity_days} روز"
        if plan.validity_days is not None
        else "بدون محدودیت زمانی ثبت‌شده"
    )
    text = (
        f"<b>{escape(plan.name)}</b>\n"
        f"حجم: <b>{format_quota(plan.quota_bytes)}</b>\n"
        f"قیمت: <b>{format_money(plan.price_amount, plan.currency)}</b>\n"
        f"اعتبار: <b>{validity}</b>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=plan_actions_keyboard(plan.id),
    )


@router.callback_query(F.data.startswith("checkout:"))
async def checkout_handler(callback: CallbackQuery, session: AsyncSession) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer()
        return

    data = callback.data or ""
    try:
        plan_id = UUID(data.removeprefix("checkout:"))
    except ValueError:
        await callback.answer("شناسه پلن معتبر نیست.", show_alert=True)
        return

    plan = await get_active_plan(session, plan_id)
    if plan is None:
        await callback.answer("این پلن دیگر فعال نیست.", show_alert=True)
        return

    user = callback.from_user
    customer = await upsert_customer(
        session,
        telegram_user_id=user.id,
        telegram_username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    key = checkout_idempotency_key(
        telegram_user_id=user.id,
        message_id=callback.message.message_id,
        plan_id=plan.id,
    )
    order, created = await get_or_create_checkout_order(
        session,
        customer=customer,
        plan=plan,
        idempotency_key=key,
    )

    await callback.answer("سفارش ثبت شد." if created else "این سفارش قبلاً ثبت شده است.")
    await callback.message.answer(
        f"شماره سفارش: <code>{order.id}</code>\n"
        f"مبلغ: <b>{format_money(order.price_amount, order.currency)}</b>\n"
        "وضعیت: <b>در انتظار پرداخت</b>\n\n"
        "مرحله بعدی، اتصال روش پرداخت به همین سفارش است."
    )


@router.message(F.text == "📦 سفارش‌های من")
async def my_orders_handler(message: Message, session: AsyncSession) -> None:
    customer = await ensure_customer(message, session)
    if customer is None:
        return

    orders = await list_customer_orders(session, customer_id=customer.id)
    if not orders:
        await message.answer("هنوز سفارشی ثبت نکرده‌اید.")
        return

    rows = []
    for order in orders:
        rows.append(
            f"<code>{order.id}</code> — "
            f"{format_quota(order.quota_bytes)} — "
            f"{format_money(order.price_amount, order.currency)} — "
            f"{order_status_label(order.status)}"
        )

    await message.answer("<b>سفارش‌های اخیر</b>\n\n" + "\n".join(rows))
