from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.keyboards.admin import admin_order_notification_keyboard
from panelprimepasar.keyboards.customer import (
    main_menu,
    payment_receipt_keyboard,
    plan_actions_keyboard,
    plans_keyboard,
)
from panelprimepasar.models import Customer, Order, OrderStatus
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.payment_methods import list_enabled_payment_methods
from panelprimepasar.services.orders import (
    checkout_idempotency_key,
    get_active_plan,
    get_or_create_checkout_order,
    list_active_plans,
    list_customer_orders,
    upsert_customer,
)
from panelprimepasar.services.payments import (
    PaymentStateError,
    create_pending_payment,
)

router = Router(name="customer")


class ReceiptForm(StatesGroup):
    waiting_receipt = State()


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

    await callback.answer(
        "سفارش ثبت شد." if created else "این سفارش قبلاً ثبت شده است."
    )

    instructions = get_settings().manual_payment_instructions
    if instructions:
        payment_text = escape(instructions)
    else:
        payment_text = (
            "اطلاعات پرداخت هنوز توسط مدیریت تنظیم نشده است؛ "
            "قبل از پرداخت با مدیریت هماهنگ کنید."
        )

    payment_methods = await list_enabled_payment_methods(session)
    await callback.message.answer(
        f"شماره سفارش: <code>{order.id}</code>\n"
        f"مبلغ: <b>{format_money(order.price_amount, order.currency)}</b>\n"
        "وضعیت: <b>در انتظار پرداخت</b>\n\n"
        f"{payment_text}\n\n"
        "پس از پرداخت، تصویر یا فایل رسید را ارسال کنید.",
        reply_markup=payment_receipt_keyboard(order.id, payment_methods),
    )


@router.callback_query(F.data.startswith("receipt:"))
async def receipt_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = callback.data or ""
    try:
        order_id = UUID(data.removeprefix("receipt:"))
    except ValueError:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    order_customer = await _customer_order(
        session,
        telegram_user_id=callback.from_user.id,
        order_id=order_id,
    )
    if order_customer is None:
        await callback.answer("سفارش پیدا نشد.", show_alert=True)
        return

    _, order = order_customer
    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        await callback.answer(
            f"وضعیت سفارش: {order_status_label(order.status)}",
            show_alert=True,
        )
        return

    await state.clear()
    await state.update_data(order_id=str(order.id))
    await state.set_state(ReceiptForm.waiting_receipt)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "تصویر رسید یا فایل رسید پرداخت را همین‌جا ارسال کنید."
        )


@router.message(ReceiptForm.waiting_receipt, F.photo | F.document)
async def receipt_received(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
) -> None:
    user = message.from_user
    if user is None:
        return

    data = await state.get_data()
    try:
        order_id = UUID(str(data["order_id"]))
    except (KeyError, ValueError):
        await state.clear()
        await message.answer("اطلاعات سفارش معتبر نیست؛ دوباره از سفارش وارد ارسال رسید شوید.")
        return

    order_customer = await _customer_order(
        session,
        telegram_user_id=user.id,
        order_id=order_id,
    )
    if order_customer is None:
        await state.clear()
        await message.answer("سفارش پیدا نشد.")
        return

    customer, order = order_customer
    if order.status not in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        await state.clear()
        await message.answer(
            f"این سفارش اکنون «{order_status_label(order.status)}» است."
        )
        return

    if message.photo:
        receipt_kind = "photo"
        file_id = message.photo[-1].file_id
    elif message.document is not None:
        receipt_kind = "document"
        file_id = message.document.file_id
    else:
        await message.answer("تصویر یا فایل رسید ارسال کنید.")
        return

    try:
        payment = await create_pending_payment(
            session,
            order_id=order.id,
            provider="manual",
            raw_reference=f"telegram:{receipt_kind}:{file_id}",
        )
    except PaymentStateError as exc:
        await session.rollback()
        await state.clear()
        await message.answer(f"ثبت رسید ناموفق بود: {escape(str(exc))}")
        return

    await record_audit_event(
        session,
        actor_type="customer",
        actor_id=str(user.id),
        action="payment.receipt_submitted",
        entity_type="order",
        entity_id=str(order.id),
        correlation_id=str(order.id),
        metadata={
            "payment_id": str(payment.id),
            "receipt_kind": receipt_kind,
        },
    )
    await session.commit()
    await state.clear()

    settings = get_settings()
    caption = (
        "<b>رسید پرداخت جدید</b>\n"
        f"سفارش: <code>{order.id}</code>\n"
        f"مشتری: <code>{customer.telegram_user_id}</code>\n"
        f"مبلغ: <b>{format_money(order.price_amount, order.currency)}</b>"
    )
    keyboard = admin_order_notification_keyboard(order.id)

    for owner_id in settings.telegram_owner_ids:
        try:
            if receipt_kind == "photo":
                await bot.send_photo(
                    owner_id,
                    file_id,
                    caption=caption,
                    reply_markup=keyboard,
                )
            else:
                await bot.send_document(
                    owner_id,
                    file_id,
                    caption=caption,
                    reply_markup=keyboard,
                )
        except TelegramAPIError:
            continue

    await message.answer(
        "رسید ثبت شد و برای بررسی مدیریت ارسال شد. "
        "پس از تأیید، وضعیت سفارش به‌روزرسانی می‌شود."
    )


@router.message(ReceiptForm.waiting_receipt)
async def receipt_invalid_message(message: Message) -> None:
    await message.answer("لطفاً تصویر یا فایل رسید پرداخت را ارسال کنید.")


@router.message(F.text == "📜 سفارش‌های من")
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
