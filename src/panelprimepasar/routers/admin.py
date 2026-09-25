from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings, get_settings
from panelprimepasar.integrations.factory import build_pasarguard_client
from panelprimepasar.integrations.pasarguard import (
    PasarGuardConfigurationError,
    PasarGuardError,
)
from panelprimepasar.keyboards.admin import (
    admin_menu,
    admin_order_actions_keyboard,
    admin_orders_keyboard,
    admin_plans_keyboard,
)
from panelprimepasar.models import Customer, Order, Plan
from panelprimepasar.routers.customer import format_money, format_quota, order_status_label
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.payments import PaymentStateError, approve_manual_order
from panelprimepasar.services.plan_inputs import (
    parse_price_toman,
    parse_quota,
    parse_validity_days,
)
from panelprimepasar.services.provisioning import (
    ProvisioningOutcome,
    ProvisioningService,
    ProvisioningStateError,
)

router = Router(name="admin")


class PlanForm(StatesGroup):
    name = State()
    quota = State()
    price = State()
    validity = State()


def _is_owner(user_id: int) -> bool:
    return user_id in get_settings().telegram_owner_ids


async def _reject_message(message: Message) -> None:
    await message.answer("دسترسی مدیریت برای این حساب فعال نیست.")


async def _reject_callback(callback: CallbackQuery) -> None:
    await callback.answer("دسترسی ندارید.", show_alert=True)


def _parse_callback_uuid(data: str | None, prefix: str) -> UUID | None:
    if data is None or not data.startswith(prefix):
        return None
    try:
        return UUID(data.removeprefix(prefix))
    except ValueError:
        return None


async def _get_order_customer(
    session: AsyncSession,
    order_id: UUID,
) -> tuple[Order, Customer] | None:
    order = await session.scalar(select(Order).where(Order.id == order_id))
    if order is None:
        return None

    customer = await session.scalar(
        select(Customer).where(Customer.id == order.customer_id)
    )
    if customer is None:
        return None
    return order, customer


def _order_details_text(order: Order, customer: Customer) -> str:
    username = (
        f"@{escape(customer.telegram_username)}"
        if customer.telegram_username
        else "بدون username"
    )
    return (
        f"<b>سفارش {str(order.id)[:8]}</b>\n\n"
        f"ID: <code>{order.id}</code>\n"
        f"مشتری: {username}\n"
        f"Telegram ID: <code>{customer.telegram_user_id}</code>\n"
        f"حجم: <b>{format_quota(order.quota_bytes)}</b>\n"
        f"مبلغ: <b>{format_money(order.price_amount, order.currency)}</b>\n"
        f"وضعیت: <b>{order_status_label(order.status)}</b>"
    )


async def _deliver_credentials(
    *,
    bot: Bot,
    settings: Settings,
    customer: Customer,
    outcome: ProvisioningOutcome,
) -> bool:
    credentials = outcome.credentials
    if credentials is None:
        return False

    panel_url = str(settings.pasarguard_base_url).rstrip("/")
    text = (
        "<b>پنل نمایندگی شما آماده است.</b>\n\n"
        f"آدرس پنل: <code>{escape(panel_url)}</code>\n"
        f"نام کاربری: <code>{escape(credentials.username)}</code>\n"
        f"رمز عبور: <code>{escape(credentials.password)}</code>\n\n"
        "رمز را در محل امن نگه‌داری کنید."
    )
    try:
        await bot.send_message(customer.telegram_user_id, text)
    except TelegramAPIError:
        return False
    return True


async def _run_provisioning(
    *,
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    order_id: UUID,
    reissue: bool,
) -> None:
    if not isinstance(callback.message, Message):
        return

    settings = get_settings()
    order_customer = await _get_order_customer(session, order_id)
    if order_customer is None:
        await callback.message.answer("سفارش یا مشتری پیدا نشد.")
        return
    _, customer = order_customer

    try:
        client = build_pasarguard_client(settings)
    except PasarGuardConfigurationError as exc:
        await callback.message.answer(
            "اتصال PasarGuard هنوز تنظیم نشده است.\n"
            f"<code>{escape(str(exc))}</code>"
        )
        return

    service = ProvisioningService(
        client=client,
        reseller_role_id=settings.pasarguard_reseller_role_id,
        reseller_role_name=settings.pasarguard_reseller_role_name,
    )

    try:
        if reissue:
            outcome = await service.reissue_credentials(
                session,
                order_id=order_id,
            )
        else:
            outcome = await service.provision_paid_order(
                session,
                order_id=order_id,
            )
    except (ProvisioningStateError, PasarGuardError) as exc:
        await session.rollback()
        await callback.message.answer(
            "عملیات ساخت پنل اجرا نشد.\n"
            f"<code>{escape(str(exc))}</code>"
        )
        return
    finally:
        await client.close()

    action = "credentials.reissued" if reissue else "provisioning.succeeded"
    if not outcome.success:
        action = "provisioning.failed"
    await record_audit_event(
        session,
        actor_type="telegram_owner",
        actor_id=str(callback.from_user.id),
        action=action,
        entity_type="order",
        entity_id=str(order_id),
        correlation_id=str(order_id),
        metadata={
            "success": outcome.success,
            "already_provisioned": outcome.already_provisioned,
            "error_code": outcome.error_code,
        },
    )
    await session.commit()

    if not outcome.success:
        await callback.message.answer(
            "ساخت پنل ناموفق بود و برای تلاش مجدد ثبت شد.\n"
            f"خطا: <code>{escape(outcome.error_code or 'unknown')}</code>\n"
            f"جزئیات: <code>{escape(outcome.error_message or '-')}</code>"
        )
        return

    if outcome.credentials is None:
        await callback.message.answer(
            "این پنل قبلاً ساخته شده است. "
            "برای ارسال مشخصات جدید از «صدور مجدد رمز و ارسال» استفاده کنید."
        )
        return

    delivered = await _deliver_credentials(
        bot=bot,
        settings=settings,
        customer=customer,
        outcome=outcome,
    )
    await record_audit_event(
        session,
        actor_type="system",
        actor_id=None,
        action=(
            "credentials.delivery_succeeded"
            if delivered
            else "credentials.delivery_failed"
        ),
        entity_type="order",
        entity_id=str(order_id),
        correlation_id=str(order_id),
        metadata={"telegram_user_id": customer.telegram_user_id},
    )
    await session.commit()

    if delivered:
        await callback.message.answer(
            "پنل ساخته شد و مشخصات برای مشتری در Telegram ارسال شد."
        )
    else:
        await callback.message.answer(
            "پنل ساخته شد، اما ارسال مشخصات به Telegram مشتری ناموفق بود. "
            "از «صدور مجدد رمز و ارسال» استفاده کنید."
        )


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await _reject_message(message)
        return

    await state.clear()
    await message.answer("مدیریت فروش پنل", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:home")
async def admin_home(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("مدیریت فروش پنل", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:create_plan")
async def create_plan_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    await callback.answer()
    await state.clear()
    await state.set_state(PlanForm.name)
    if isinstance(callback.message, Message):
        await callback.message.answer("نام پلن را وارد کنید. مثال: پنل 1 ترابایت")


@router.message(PlanForm.name)
async def create_plan_name(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await _reject_message(message)
        return

    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 128:
        await message.answer("نام پلن باید بین 2 تا 128 کاراکتر باشد.")
        return

    await state.update_data(name=name)
    await state.set_state(PlanForm.quota)
    await message.answer(
        "حجم را با واحد وارد کنید. مثال:\n"
        "<code>500GB</code>\n"
        "<code>1TB</code>\n"
        "<code>1TiB</code>"
    )


@router.message(PlanForm.quota)
async def create_plan_quota(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await _reject_message(message)
        return

    try:
        quota_bytes = parse_quota(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(quota_bytes=quota_bytes)
    await state.set_state(PlanForm.price)
    await message.answer("قیمت را به تومان وارد کنید. مثال: <code>200000</code>")


@router.message(PlanForm.price)
async def create_plan_price(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await _reject_message(message)
        return

    try:
        price_amount = parse_price_toman(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.update_data(price_amount=price_amount)
    await state.set_state(PlanForm.validity)
    await message.answer(
        "اعتبار پلن را به روز وارد کنید. "
        "برای بدون محدودیت زمانی عدد <code>0</code> بفرستید."
    )


@router.message(PlanForm.validity)
async def create_plan_validity(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = message.from_user
    if user is None or not _is_owner(user.id):
        await _reject_message(message)
        return

    try:
        validity_days = parse_validity_days(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return

    data = await state.get_data()
    name = str(data["name"])
    quota_bytes = int(data["quota_bytes"])
    price_amount = int(data["price_amount"])

    duplicate = await session.scalar(select(Plan).where(Plan.name == name))
    if duplicate is not None:
        await message.answer("پلنی با این نام از قبل وجود دارد. نام دیگری انتخاب کنید.")
        await state.set_state(PlanForm.name)
        return

    plan = Plan(
        name=name,
        quota_bytes=quota_bytes,
        price_amount=price_amount,
        currency="IRT",
        validity_days=validity_days,
        is_active=True,
        sort_order=0,
    )
    session.add(plan)
    await session.flush()
    await record_audit_event(
        session,
        actor_type="telegram_owner",
        actor_id=str(user.id),
        action="plan.created",
        entity_type="plan",
        entity_id=str(plan.id),
        correlation_id=str(plan.id),
        metadata={
            "quota_bytes": plan.quota_bytes,
            "price_amount": plan.price_amount,
            "currency": plan.currency,
            "validity_days": plan.validity_days,
        },
    )
    await state.clear()

    validity_text = (
        f"{validity_days} روز"
        if validity_days is not None
        else "بدون محدودیت"
    )
    await message.answer(
        "پلن ساخته شد.\n\n"
        f"نام: <b>{escape(plan.name)}</b>\n"
        f"حجم: <b>{format_quota(plan.quota_bytes)}</b>\n"
        f"قیمت: <b>{format_money(plan.price_amount, plan.currency)}</b>\n"
        f"اعتبار: <b>{validity_text}</b>",
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "admin:plans")
async def admin_plans(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    await callback.answer()
    plans = list(
        (
            await session.scalars(
                select(Plan).order_by(Plan.sort_order.asc(), Plan.created_at.desc())
            )
        ).all()
    )
    if not isinstance(callback.message, Message):
        return

    if not plans:
        await callback.message.answer(
            "هنوز پلنی ساخته نشده است.",
            reply_markup=admin_menu(),
        )
        return

    await callback.message.answer(
        "برای فعال/غیرفعال کردن هر پلن روی آن بزنید.",
        reply_markup=admin_plans_keyboard(plans),
    )


@router.callback_query(F.data.startswith("admin:toggle_plan:"))
async def toggle_plan(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    plan_id = _parse_callback_uuid(callback.data, "admin:toggle_plan:")
    if plan_id is None:
        await callback.answer("شناسه پلن معتبر نیست.", show_alert=True)
        return

    plan = await session.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None:
        await callback.answer("پلن پیدا نشد.", show_alert=True)
        return

    plan.is_active = not plan.is_active
    await session.flush()
    await record_audit_event(
        session,
        actor_type="telegram_owner",
        actor_id=str(callback.from_user.id),
        action="plan.status_changed",
        entity_type="plan",
        entity_id=str(plan.id),
        correlation_id=str(plan.id),
        metadata={"is_active": plan.is_active},
    )
    await callback.answer("وضعیت پلن تغییر کرد.")

    plans = list(
        (
            await session.scalars(
                select(Plan).order_by(Plan.sort_order.asc(), Plan.created_at.desc())
            )
        ).all()
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(
            reply_markup=admin_plans_keyboard(plans)
        )


@router.callback_query(F.data == "admin:orders")
async def admin_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    await callback.answer()
    orders = list(
        (
            await session.scalars(
                select(Order).order_by(Order.created_at.desc()).limit(20)
            )
        ).all()
    )
    if not isinstance(callback.message, Message):
        return

    if not orders:
        await callback.message.answer(
            "هنوز سفارشی ثبت نشده است.",
            reply_markup=admin_menu(),
        )
        return

    await callback.message.answer(
        "20 سفارش اخیر:",
        reply_markup=admin_orders_keyboard(orders),
    )


@router.callback_query(F.data.startswith("admin:order:"))
async def admin_order_details(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    order_id = _parse_callback_uuid(callback.data, "admin:order:")
    if order_id is None:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    order_customer = await _get_order_customer(session, order_id)
    if order_customer is None:
        await callback.answer("سفارش پیدا نشد.", show_alert=True)
        return

    order, customer = order_customer
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            _order_details_text(order, customer),
            reply_markup=admin_order_actions_keyboard(order),
        )


@router.callback_query(F.data.startswith("admin:approve:"))
async def approve_order(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    order_id = _parse_callback_uuid(callback.data, "admin:approve:")
    if order_id is None:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    await callback.answer("در حال تأیید و ساخت پنل...")
    try:
        payment = await approve_manual_order(
            session,
            order_id=order_id,
            actor_telegram_id=callback.from_user.id,
        )
        await record_audit_event(
            session,
            actor_type="telegram_owner",
            actor_id=str(callback.from_user.id),
            action="payment.manual_approved",
            entity_type="order",
            entity_id=str(order_id),
            correlation_id=str(order_id),
            metadata={
                "payment_id": str(payment.id),
                "provider": payment.provider,
                "amount": payment.amount,
                "currency": payment.currency,
            },
        )
        await session.commit()
    except PaymentStateError as exc:
        await session.rollback()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"پرداخت تأیید نشد: <code>{escape(str(exc))}</code>"
            )
        return

    await _run_provisioning(
        callback=callback,
        bot=bot,
        session=session,
        order_id=order_id,
        reissue=False,
    )


@router.callback_query(F.data.startswith("admin:provision:"))
async def provision_order(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    order_id = _parse_callback_uuid(callback.data, "admin:provision:")
    if order_id is None:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    await callback.answer("در حال ساخت پنل...")
    await _run_provisioning(
        callback=callback,
        bot=bot,
        session=session,
        order_id=order_id,
        reissue=False,
    )


@router.callback_query(F.data.startswith("admin:reissue:"))
async def reissue_order_credentials(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
) -> None:
    if not _is_owner(callback.from_user.id):
        await _reject_callback(callback)
        return

    order_id = _parse_callback_uuid(callback.data, "admin:reissue:")
    if order_id is None:
        await callback.answer("شناسه سفارش معتبر نیست.", show_alert=True)
        return

    await callback.answer("در حال صدور رمز جدید...")
    await _run_provisioning(
        callback=callback,
        bot=bot,
        session=session,
        order_id=order_id,
        reissue=True,
    )
