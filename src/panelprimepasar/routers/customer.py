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
    lifecycle_plans_keyboard,
    main_menu,
    payment_receipt_keyboard,
    plan_actions_keyboard,
    plans_keyboard,
    subscription_actions_keyboard,
    subscriptions_keyboard,
)
from panelprimepasar.models import Customer, Order, OrderKind, OrderStatus
from panelprimepasar.services.audit import record_audit_event
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
from panelprimepasar.services.subscriptions import (
    create_lifecycle_order,
    get_customer_subscription,
    list_customer_subscriptions,
)
from panelprimepasar.services.support import (
    SupportStateError,
    create_ticket,
    list_customer_tickets,
)

router = Router(name="customer")


class ReceiptForm(StatesGroup):
    waiting_receipt = State()


class SupportForm(StatesGroup):
    subject = State()
    body = State()


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

    await callback.message.answer(
        f"شماره سفارش: <code>{order.id}</code>\n"
        f"مبلغ: <b>{format_money(order.price_amount, order.currency)}</b>\n"
        "وضعیت: <b>در انتظار پرداخت</b>\n\n"
        f"{payment_text}\n\n"
        "پس از پرداخت، تصویر یا فایل رسید را ارسال کنید.",
        reply_markup=payment_receipt_keyboard(order.id),
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



@router.message(F.text == "📡 سرویس‌های من")
async def my_services_handler(message: Message, session: AsyncSession) -> None:
    customer = await ensure_customer(message, session)
    if customer is None:
        return
    subscriptions = await list_customer_subscriptions(session, customer_id=customer.id)
    if not subscriptions:
        await message.answer("هنوز سرویس فعالی برای حساب شما ثبت نشده است.")
        return
    await message.answer(
        "سرویس موردنظر را انتخاب کنید:",
        reply_markup=subscriptions_keyboard(subscriptions),
    )


@router.callback_query(F.data == "services")
async def my_services_callback(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    user = callback.from_user
    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == user.id)
    )
    if customer is None or not isinstance(callback.message, Message):
        return
    subscriptions = await list_customer_subscriptions(session, customer_id=customer.id)
    if not subscriptions:
        await callback.message.answer("هنوز سرویسی برای حساب شما ثبت نشده است.")
        return
    await callback.message.answer(
        "سرویس موردنظر را انتخاب کنید:",
        reply_markup=subscriptions_keyboard(subscriptions),
    )


@router.callback_query(F.data.startswith("service:"))
async def service_details(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        subscription_id = UUID((callback.data or "").removeprefix("service:"))
    except ValueError:
        await callback.answer("شناسه سرویس معتبر نیست.", show_alert=True)
        return

    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == callback.from_user.id)
    )
    if customer is None:
        await callback.answer("حساب مشتری پیدا نشد.", show_alert=True)
        return

    subscription = await get_customer_subscription(
        session,
        customer_id=customer.id,
        subscription_id=subscription_id,
    )
    if subscription is None:
        await callback.answer("سرویس پیدا نشد.", show_alert=True)
        return

    expires = (
        subscription.expires_at.strftime("%Y-%m-%d %H:%M UTC")
        if subscription.expires_at is not None
        else "بدون تاریخ انقضا"
    )
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"<b>سرویس {str(subscription.id)[:8]}</b>\n\n"
            f"وضعیت: <b>{escape(subscription.status)}</b>\n"
            f"حجم: <b>{format_quota(subscription.quota_bytes)}</b>\n"
            f"انقضا: <b>{expires}</b>",
            reply_markup=subscription_actions_keyboard(subscription.id),
        )


async def _lifecycle_catalog(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    action: str,
) -> None:
    prefix = f"service_{action}:"
    try:
        subscription_id = UUID((callback.data or "").removeprefix(prefix))
    except ValueError:
        await callback.answer("شناسه سرویس معتبر نیست.", show_alert=True)
        return

    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == callback.from_user.id)
    )
    if customer is None:
        await callback.answer("حساب مشتری پیدا نشد.", show_alert=True)
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
    await callback.answer()
    if isinstance(callback.message, Message):
        if not plans:
            await callback.message.answer("در حال حاضر پلن فعالی وجود ندارد.")
            return
        title = "پلن تمدید را انتخاب کنید:" if action == "renew" else "بسته افزایش حجم را انتخاب کنید:"
        await callback.message.answer(
            title,
            reply_markup=lifecycle_plans_keyboard(
                plans,
                subscription_id=subscription.id,
                action=action,
            ),
        )


@router.callback_query(F.data.startswith("service_renew:"))
async def renewal_catalog(callback: CallbackQuery, session: AsyncSession) -> None:
    await _lifecycle_catalog(callback, session, action="renew")


@router.callback_query(F.data.startswith("service_topup:"))
async def topup_catalog(callback: CallbackQuery, session: AsyncSession) -> None:
    await _lifecycle_catalog(callback, session, action="topup")


@router.callback_query(F.data.startswith("renew_plan:") | F.data.startswith("topup_plan:"))
async def lifecycle_checkout(callback: CallbackQuery, session: AsyncSession) -> None:
    data = callback.data or ""
    action = "renew" if data.startswith("renew_plan:") else "topup"
    payload = data.removeprefix(f"{action}_plan:")
    try:
        subscription_raw, plan_raw = payload.split(":", maxsplit=1)
        subscription_id = UUID(subscription_raw)
        plan_id = UUID(plan_raw)
    except (ValueError, TypeError):
        await callback.answer("اطلاعات سفارش معتبر نیست.", show_alert=True)
        return

    customer = await session.scalar(
        select(Customer).where(Customer.telegram_user_id == callback.from_user.id)
    )
    if customer is None:
        await callback.answer("حساب مشتری پیدا نشد.", show_alert=True)
        return
    subscription = await get_customer_subscription(
        session,
        customer_id=customer.id,
        subscription_id=subscription_id,
    )
    plan = await get_active_plan(session, plan_id)
    if subscription is None or plan is None:
        await callback.answer("سرویس یا پلن در دسترس نیست.", show_alert=True)
        return

    kind = OrderKind.RENEWAL if action == "renew" else OrderKind.TOPUP
    message_id = callback.message.message_id if isinstance(callback.message, Message) else 0
    key = f"lifecycle:{callback.from_user.id}:{message_id}:{subscription.id}:{plan.id}:{kind.value}"
    order, created = await create_lifecycle_order(
        session,
        customer=customer,
        subscription=subscription,
        plan=plan,
        kind=kind,
        idempotency_key=key,
    )
    await callback.answer("سفارش ثبت شد." if created else "این سفارش قبلاً ثبت شده است.")
    if not isinstance(callback.message, Message):
        return

    instructions = get_settings().manual_payment_instructions
    payment_text = (
        escape(instructions)
        if instructions
        else "اطلاعات پرداخت هنوز توسط مدیریت تنظیم نشده است."
    )
    await callback.message.answer(
        f"شماره سفارش: <code>{order.id}</code>\n"
        f"نوع: <b>{'تمدید' if kind == OrderKind.RENEWAL else 'افزایش حجم'}</b>\n"
        f"مبلغ: <b>{format_money(order.price_amount, order.currency)}</b>\n\n"
        f"{payment_text}\n\n"
        "پس از پرداخت، رسید را ارسال کنید.",
        reply_markup=payment_receipt_keyboard(order.id),
    )


@router.message(F.text == "👤 حساب من")
async def profile_handler(message: Message, session: AsyncSession) -> None:
    customer = await ensure_customer(message, session)
    if customer is None:
        return
    subscriptions = await list_customer_subscriptions(session, customer_id=customer.id)
    orders = await list_customer_orders(session, customer_id=customer.id)
    active_count = sum(1 for item in subscriptions if item.status == "active")
    username = f"@{escape(customer.telegram_username)}" if customer.telegram_username else "ثبت نشده"
    await message.answer(
        "<b>حساب کاربری</b>\n\n"
        f"Telegram ID: <code>{customer.telegram_user_id}</code>\n"
        f"Username: {username}\n"
        f"تعداد سفارش‌ها: <b>{len(orders)}</b>\n"
        f"سرویس‌های فعال: <b>{active_count}</b>"
    )


@router.message(F.text == "🎧 پشتیبانی")
async def support_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    customer = await ensure_customer(message, session)
    if customer is None:
        return
    tickets = await list_customer_tickets(session, customer_id=customer.id)
    await state.clear()
    recent = "\n".join(
        f"• <code>{ticket.id}</code> — {escape(ticket.subject)} — {escape(ticket.status)}"
        for ticket in tickets[:5]
    )
    await message.answer(
        "<b>پشتیبانی</b>\n\n"
        + (f"تیکت‌های اخیر:\n{recent}\n\n" if recent else "")
        + "برای ساخت تیکت جدید، موضوع را ارسال کنید."
    )
    await state.set_state(SupportForm.subject)


@router.message(SupportForm.subject)
async def support_subject(message: Message, state: FSMContext) -> None:
    subject = (message.text or "").strip()
    if not subject or len(subject) > 160:
        await message.answer("موضوع باید بین 1 تا 160 کاراکتر باشد.")
        return
    await state.update_data(subject=subject)
    await state.set_state(SupportForm.body)
    await message.answer("متن درخواست پشتیبانی را ارسال کنید.")


@router.message(SupportForm.body)
async def support_body(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    customer = await ensure_customer(message, session)
    if customer is None:
        return
    body = (message.text or "").strip()
    data = await state.get_data()
    subject = str(data.get("subject", ""))
    try:
        ticket = await create_ticket(
            session,
            customer_id=customer.id,
            subject=subject,
            body=body,
        )
    except SupportStateError as exc:
        await message.answer(escape(str(exc)))
        return

    await record_audit_event(
        session,
        actor_type="customer",
        actor_id=str(customer.telegram_user_id),
        action="support.ticket_created",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        correlation_id=str(ticket.id),
    )
    await session.commit()
    await state.clear()

    await message.answer(
        f"تیکت ثبت شد.\nشناسه: <code>{ticket.id}</code>",
        reply_markup=main_menu(),
    )
    for owner_id in get_settings().telegram_owner_ids:
        try:
            await bot.send_message(
                owner_id,
                "<b>تیکت پشتیبانی جدید</b>\n"
                f"شناسه: <code>{ticket.id}</code>\n"
                f"مشتری: <code>{customer.telegram_user_id}</code>\n"
                f"موضوع: {escape(ticket.subject)}",
            )
        except TelegramAPIError:
            continue


@router.message(F.text == "ℹ️ راهنما")
async def help_handler(message: Message) -> None:
    await message.answer(
        "<b>راهنمای ربات</b>\n\n"
        "🛒 خرید پنل: انتخاب و ثبت سفارش جدید\n"
        "📡 سرویس‌های من: مشاهده، تمدید و افزایش حجم\n"
        "📦 سفارش‌های من: پیگیری وضعیت سفارش‌ها\n"
        "👤 حساب من: خلاصه حساب و سرویس‌ها\n"
        "🎧 پشتیبانی: ثبت تیکت برای مدیریت"
    )
