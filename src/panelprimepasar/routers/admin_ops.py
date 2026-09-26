from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.keyboards.admin import admin_menu
from panelprimepasar.keyboards.admin_ops import (
    staff_admins_keyboard,
    staff_role_keyboard,
    support_ticket_actions_keyboard,
    support_tickets_keyboard,
)
from panelprimepasar.models import (
    AuditEvent,
    Customer,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    StaffAdmin,
    Subscription,
    SubscriptionStatus,
    SupportTicket,
    TicketStatus,
)
from panelprimepasar.security import AdminRole, Permission
from panelprimepasar.services.admins import (
    AdminAccessError,
    admin_has_permission,
    list_staff_admins,
    set_staff_admin_active,
    upsert_staff_admin,
)
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.support import (
    SupportStateError,
    add_staff_message,
    close_ticket_by_staff,
    get_ticket_messages,
    list_support_tickets,
)

router = Router(name="admin_operations")


class SupportReplyForm(StatesGroup):
    body = State()


class StaffAddForm(StatesGroup):
    telegram_id = State()


async def _allowed(
    session: AsyncSession,
    *,
    user_id: int,
    permission: Permission,
) -> bool:
    return await admin_has_permission(
        session,
        telegram_user_id=user_id,
        permission=permission,
    )


async def _deny(callback: CallbackQuery) -> None:
    await callback.answer("دسترسی ندارید.", show_alert=True)


@router.callback_query(F.data == "admin:dashboard")
async def dashboard(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.VIEW_DASHBOARD,
    ):
        await _deny(callback)
        return

    customers = int(await session.scalar(select(func.count(Customer.id))) or 0)
    active_services = int(
        await session.scalar(
            select(func.count(Subscription.id)).where(
                Subscription.status == SubscriptionStatus.ACTIVE.value
            )
        )
        or 0
    )
    pending_orders = int(
        await session.scalar(
            select(func.count(Order.id)).where(
                Order.status.in_(
                    [
                        OrderStatus.PENDING,
                        OrderStatus.AWAITING_PAYMENT,
                        OrderStatus.PAID,
                        OrderStatus.PROVISIONING,
                    ]
                )
            )
        )
        or 0
    )
    pending_payments = int(
        await session.scalar(
            select(func.count(Payment.id)).where(
                Payment.status == PaymentStatus.PENDING
            )
        )
        or 0
    )
    revenue = int(
        await session.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == PaymentStatus.VERIFIED
            )
        )
        or 0
    )

    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "<b>داشبورد</b>\n\n"
            f"👥 کاربران: <b>{customers}</b>\n"
            f"📦 سرویس فعال: <b>{active_services}</b>\n"
            f"🧾 سفارش در جریان: <b>{pending_orders}</b>\n"
            f"💳 پرداخت در انتظار: <b>{pending_payments}</b>\n"
            f"💰 فروش تأییدشده: <b>{revenue:,} IRT</b>",
            reply_markup=admin_menu(),
        )


@router.callback_query(F.data == "admin:customers")
async def customers(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.VIEW_USERS,
    ):
        await _deny(callback)
        return

    rows = list(
        (
            await session.scalars(
                select(Customer)
                .order_by(Customer.created_at.desc(), Customer.id.desc())
                .limit(20)
            )
        ).all()
    )
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    if not rows:
        await callback.message.answer("هنوز کاربری ثبت نشده است.", reply_markup=admin_menu())
        return

    lines = []
    for customer in rows:
        username = f"@{customer.telegram_username}" if customer.telegram_username else "-"
        state = "🚫" if customer.is_blocked else "✅"
        lines.append(
            f"{state} <code>{customer.telegram_user_id}</code> · {escape(username)}"
        )
    await callback.message.answer(
        "<b>20 کاربر اخیر</b>\n\n" + "\n".join(lines),
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "admin:payments")
async def payments(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.VIEW_PAYMENTS,
    ):
        await _deny(callback)
        return

    rows = list(
        (
            await session.scalars(
                select(Payment)
                .order_by(Payment.created_at.desc(), Payment.id.desc())
                .limit(20)
            )
        ).all()
    )
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    if not rows:
        await callback.message.answer("پرداختی ثبت نشده است.", reply_markup=admin_menu())
        return

    lines = [
        (
            f"<code>{str(payment.id)[:8]}</code> · "
            f"{payment.amount:,} {escape(payment.currency)} · "
            f"{escape(payment.status.value)} · {escape(payment.provider)}"
        )
        for payment in rows
    ]
    await callback.message.answer(
        "<b>20 پرداخت اخیر</b>\n\n" + "\n".join(lines),
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "admin:audit")
async def audit(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.VIEW_AUDIT_LOGS,
    ):
        await _deny(callback)
        return

    rows = list(
        (
            await session.scalars(
                select(AuditEvent)
                .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
                .limit(20)
            )
        ).all()
    )
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    if not rows:
        await callback.message.answer("لاگی ثبت نشده است.", reply_markup=admin_menu())
        return

    lines = [
        (
            f"<code>{event.created_at:%Y-%m-%d %H:%M}</code> · "
            f"{escape(event.action)} · {escape(event.entity_type)}"
        )
        for event in rows
    ]
    await callback.message.answer(
        "<b>Audit Log</b>\n\n" + "\n".join(lines),
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data == "admin:support")
async def support(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_SUPPORT,
    ):
        await _deny(callback)
        return

    tickets = await list_support_tickets(session, limit=20)
    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    if not tickets:
        await callback.message.answer("تیکتی ثبت نشده است.", reply_markup=admin_menu())
        return

    await callback.message.answer(
        "تیکت‌های اخیر:",
        reply_markup=support_tickets_keyboard(tickets),
    )


@router.callback_query(F.data.startswith("admin:ticket:"))
async def support_ticket_detail(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_SUPPORT,
    ):
        await _deny(callback)
        return

    try:
        ticket_id = UUID(hex=(callback.data or "").removeprefix("admin:ticket:"))
    except ValueError:
        await callback.answer("شناسه تیکت معتبر نیست.", show_alert=True)
        return

    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None:
        await callback.answer("تیکت پیدا نشد.", show_alert=True)
        return

    messages = await get_ticket_messages(session, ticket_id=ticket.id)
    customer = await session.get(Customer, ticket.customer_id)
    body_lines = []
    for item in messages[-10:]:
        sender = "👤" if item.sender_type == "customer" else "🛠"
        body_lines.append(f"{sender} {escape(item.body)}")

    await callback.answer()
    if isinstance(callback.message, Message):
        customer_text = (
            str(customer.telegram_user_id)
            if customer is not None
            else "unknown"
        )
        await callback.message.answer(
            f"<b>{escape(ticket.subject)}</b>\n"
            f"شناسه: <code>{ticket.id}</code>\n"
            f"کاربر: <code>{customer_text}</code>\n"
            f"وضعیت: <b>{escape(ticket.status)}</b>\n\n"
            + ("\n\n".join(body_lines) if body_lines else "بدون پیام"),
            reply_markup=support_ticket_actions_keyboard(ticket.id),
        )


@router.callback_query(F.data.startswith("admin:ticket_reply:"))
async def support_reply_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_SUPPORT,
    ):
        await _deny(callback)
        return

    try:
        ticket_id = UUID(
            hex=(callback.data or "").removeprefix("admin:ticket_reply:")
        )
    except ValueError:
        await callback.answer("شناسه تیکت معتبر نیست.", show_alert=True)
        return

    ticket = await session.get(SupportTicket, ticket_id)
    if ticket is None or ticket.status == TicketStatus.CLOSED.value:
        await callback.answer("این تیکت قابل پاسخ نیست.", show_alert=True)
        return

    await state.clear()
    await state.update_data(ticket_id=str(ticket.id))
    await state.set_state(SupportReplyForm.body)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("پاسخ پشتیبانی را ارسال کنید.")


@router.message(SupportReplyForm.body)
async def support_reply_body(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None or not await _allowed(
        session,
        user_id=message.from_user.id,
        permission=Permission.MANAGE_SUPPORT,
    ):
        await message.answer("دسترسی ندارید.")
        return

    data = await state.get_data()
    try:
        ticket_id = UUID(str(data["ticket_id"]))
    except (KeyError, ValueError):
        await state.clear()
        await message.answer("اطلاعات تیکت معتبر نیست.")
        return

    try:
        ticket, support_message = await add_staff_message(
            session,
            ticket_id=ticket_id,
            staff_telegram_id=message.from_user.id,
            body=message.text or "",
        )
    except SupportStateError as exc:
        await message.answer(escape(str(exc)))
        return

    await record_audit_event(
        session,
        actor_type="telegram_staff",
        actor_id=str(message.from_user.id),
        action="support.replied",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        correlation_id=str(ticket.id),
    )
    await session.commit()
    await state.clear()

    customer = await session.get(Customer, ticket.customer_id)
    if customer is not None:
        try:
            await bot.send_message(
                customer.telegram_user_id,
                "<b>پاسخ پشتیبانی</b>\n"
                f"تیکت: <code>{ticket.id}</code>\n\n"
                f"{escape(support_message.body)}",
            )
        except TelegramAPIError:
            pass

    await message.answer("پاسخ ثبت و برای مشتری ارسال شد.", reply_markup=admin_menu())


@router.callback_query(F.data.startswith("admin:ticket_close:"))
async def support_ticket_close(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_SUPPORT,
    ):
        await _deny(callback)
        return

    try:
        ticket_id = UUID(
            hex=(callback.data or "").removeprefix("admin:ticket_close:")
        )
    except ValueError:
        await callback.answer("شناسه تیکت معتبر نیست.", show_alert=True)
        return

    try:
        ticket = await close_ticket_by_staff(session, ticket_id=ticket_id)
    except SupportStateError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await record_audit_event(
        session,
        actor_type="telegram_staff",
        actor_id=str(callback.from_user.id),
        action="support.closed",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        correlation_id=str(ticket.id),
    )
    await session.commit()
    await callback.answer("تیکت بسته شد.")


@router.callback_query(F.data == "admin:staff")
async def staff_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_ADMINS,
    ):
        await _deny(callback)
        return

    staff = await list_staff_admins(session)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "مدیران ربات:",
            reply_markup=staff_admins_keyboard(staff),
        )


@router.callback_query(F.data == "admin:staff_add")
async def staff_add_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_ADMINS,
    ):
        await _deny(callback)
        return

    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "نقش مدیر جدید را انتخاب کنید:",
            reply_markup=staff_role_keyboard(),
        )


@router.callback_query(F.data.startswith("admin:staff_role:"))
async def staff_role_selected(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_ADMINS,
    ):
        await _deny(callback)
        return

    raw_role = (callback.data or "").removeprefix("admin:staff_role:")
    try:
        role = AdminRole(raw_role)
    except ValueError:
        await callback.answer("نقش معتبر نیست.", show_alert=True)
        return

    if role == AdminRole.OWNER:
        await callback.answer("Owner از env مدیریت می‌شود.", show_alert=True)
        return

    await state.update_data(staff_role=role.value)
    await state.set_state(StaffAddForm.telegram_id)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("Telegram ID مدیر جدید را ارسال کنید.")


@router.message(StaffAddForm.telegram_id)
async def staff_add_telegram_id(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None or not await _allowed(
        session,
        user_id=message.from_user.id,
        permission=Permission.MANAGE_ADMINS,
    ):
        await message.answer("دسترسی ندارید.")
        return

    raw_id = (message.text or "").strip()
    if not raw_id.isdecimal():
        await message.answer("Telegram ID باید عددی باشد.")
        return

    data = await state.get_data()
    try:
        role = AdminRole(str(data["staff_role"]))
        telegram_user_id = int(raw_id)
        staff = await upsert_staff_admin(
            session,
            telegram_user_id=telegram_user_id,
            role=role,
        )
    except (KeyError, ValueError, AdminAccessError) as exc:
        await message.answer(escape(str(exc)))
        return

    await record_audit_event(
        session,
        actor_type="telegram_owner",
        actor_id=str(message.from_user.id),
        action="staff.upserted",
        entity_type="staff_admin",
        entity_id=str(staff.id),
        correlation_id=str(staff.id),
        metadata={
            "telegram_user_id": telegram_user_id,
            "role": role.value,
        },
    )
    await session.commit()
    await state.clear()
    await message.answer(
        f"مدیر <code>{telegram_user_id}</code> با نقش <b>{role.value}</b> ذخیره شد.",
        reply_markup=admin_menu(),
    )


@router.callback_query(F.data.startswith("admin:staff_toggle:"))
async def staff_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if not await _allowed(
        session,
        user_id=callback.from_user.id,
        permission=Permission.MANAGE_ADMINS,
    ):
        await _deny(callback)
        return

    try:
        staff_id = UUID(
            hex=(callback.data or "").removeprefix("admin:staff_toggle:")
        )
    except ValueError:
        await callback.answer("شناسه مدیر معتبر نیست.", show_alert=True)
        return

    staff = await session.get(StaffAdmin, staff_id)
    if staff is None:
        await callback.answer("مدیر پیدا نشد.", show_alert=True)
        return

    try:
        staff = await set_staff_admin_active(
            session,
            staff_id=staff.id,
            is_active=not staff.is_active,
        )
    except AdminAccessError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await record_audit_event(
        session,
        actor_type="telegram_owner",
        actor_id=str(callback.from_user.id),
        action="staff.status_changed",
        entity_type="staff_admin",
        entity_id=str(staff.id),
        correlation_id=str(staff.id),
        metadata={"is_active": staff.is_active},
    )
    await session.commit()
    await callback.answer("وضعیت مدیر تغییر کرد.")
