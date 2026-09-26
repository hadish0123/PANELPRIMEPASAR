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
from panelprimepasar.keyboards.customer import main_menu
from panelprimepasar.keyboards.support import (
    support_home_keyboard,
    support_ticket_keyboard,
)
from panelprimepasar.models import Customer, SupportTicket, TicketStatus
from panelprimepasar.services.audit import record_audit_event
from panelprimepasar.services.support import (
    SupportStateError,
    add_customer_message,
    close_ticket,
    create_ticket,
    get_ticket_messages,
    list_customer_tickets,
)

router = Router(name="customer_support")


class NewTicketForm(StatesGroup):
    subject = State()
    body = State()


class ReplyTicketForm(StatesGroup):
    body = State()


async def _customer(
    session: AsyncSession,
    *,
    telegram_user_id: int,
) -> Customer | None:
    return await session.scalar(
        select(Customer).where(Customer.telegram_user_id == telegram_user_id)
    )


async def _show_home(
    message: Message,
    *,
    session: AsyncSession,
    customer: Customer,
) -> None:
    tickets = await list_customer_tickets(
        session,
        customer_id=customer.id,
        limit=10,
    )
    await message.answer(
        "<b>پشتیبانی</b>\n"
        "تیکت جدید بسازید یا یکی از تیکت‌های قبلی را باز کنید.",
        reply_markup=support_home_keyboard(tickets),
    )


@router.message(F.text == "🎧 پشتیبانی")
async def support_home_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return

    customer = await _customer(
        session,
        telegram_user_id=message.from_user.id,
    )
    if customer is None:
        await message.answer("ابتدا /start را ارسال کنید.")
        return

    await state.clear()
    await _show_home(message, session=session, customer=customer)


@router.callback_query(F.data == "support:home")
async def support_home_callback(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    customer = await _customer(
        session,
        telegram_user_id=callback.from_user.id,
    )
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await _show_home(callback.message, session=session, customer=customer)


@router.callback_query(F.data == "support:new")
async def support_new(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await state.set_state(NewTicketForm.subject)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("موضوع تیکت را ارسال کنید.")


@router.message(NewTicketForm.subject)
async def support_new_subject(
    message: Message,
    state: FSMContext,
) -> None:
    subject = (message.text or "").strip()
    if not subject or len(subject) > 160:
        await message.answer("موضوع باید بین 1 تا 160 کاراکتر باشد.")
        return

    await state.update_data(subject=subject)
    await state.set_state(NewTicketForm.body)
    await message.answer("متن درخواست پشتیبانی را ارسال کنید.")


@router.message(NewTicketForm.body)
async def support_new_body(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    customer = await _customer(
        session,
        telegram_user_id=message.from_user.id,
    )
    if customer is None:
        await state.clear()
        await message.answer("حساب کاربری پیدا نشد.")
        return

    data = await state.get_data()
    try:
        ticket = await create_ticket(
            session,
            customer_id=customer.id,
            subject=str(data.get("subject", "")),
            body=message.text or "",
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
        reply_markup=support_ticket_keyboard(ticket.id, is_closed=False),
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


@router.callback_query(F.data.startswith("support:ticket:"))
async def support_ticket_detail(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        ticket_id = UUID(
            hex=(callback.data or "").removeprefix("support:ticket:")
        )
    except ValueError:
        await callback.answer("شناسه تیکت معتبر نیست.", show_alert=True)
        return

    customer = await _customer(
        session,
        telegram_user_id=callback.from_user.id,
    )
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    ticket = await session.scalar(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.customer_id == customer.id,
        )
    )
    if ticket is None:
        await callback.answer("تیکت پیدا نشد.", show_alert=True)
        return

    messages = await get_ticket_messages(
        session,
        ticket_id=ticket.id,
        limit=20,
    )
    transcript = []
    for item in messages:
        sender = "👤 شما" if item.sender_type == "customer" else "🛠 پشتیبانی"
        transcript.append(f"<b>{sender}</b>\n{escape(item.body)}")

    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            f"<b>{escape(ticket.subject)}</b>\n"
            f"شناسه: <code>{ticket.id}</code>\n"
            f"وضعیت: <b>{escape(ticket.status)}</b>\n\n"
            + ("\n\n".join(transcript) if transcript else "بدون پیام"),
            reply_markup=support_ticket_keyboard(
                ticket.id,
                is_closed=ticket.status == TicketStatus.CLOSED.value,
            ),
        )


@router.callback_query(F.data.startswith("support:reply:"))
async def support_reply_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        ticket_id = UUID(
            hex=(callback.data or "").removeprefix("support:reply:")
        )
    except ValueError:
        await callback.answer("شناسه تیکت معتبر نیست.", show_alert=True)
        return

    customer = await _customer(
        session,
        telegram_user_id=callback.from_user.id,
    )
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    ticket = await session.scalar(
        select(SupportTicket).where(
            SupportTicket.id == ticket_id,
            SupportTicket.customer_id == customer.id,
        )
    )
    if ticket is None or ticket.status == TicketStatus.CLOSED.value:
        await callback.answer("این تیکت قابل پاسخ نیست.", show_alert=True)
        return

    await state.clear()
    await state.update_data(ticket_id=str(ticket.id))
    await state.set_state(ReplyTicketForm.body)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer("پیام جدید را ارسال کنید.")


@router.message(ReplyTicketForm.body)
async def support_reply_body(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if message.from_user is None:
        return

    customer = await _customer(
        session,
        telegram_user_id=message.from_user.id,
    )
    if customer is None:
        await state.clear()
        await message.answer("حساب کاربری پیدا نشد.")
        return

    data = await state.get_data()
    try:
        ticket_id = UUID(str(data["ticket_id"]))
        support_message = await add_customer_message(
            session,
            customer_id=customer.id,
            ticket_id=ticket_id,
            body=message.text or "",
        )
    except (KeyError, ValueError, SupportStateError) as exc:
        await message.answer(escape(str(exc)))
        return

    await record_audit_event(
        session,
        actor_type="customer",
        actor_id=str(customer.telegram_user_id),
        action="support.customer_replied",
        entity_type="support_ticket",
        entity_id=str(ticket_id),
        correlation_id=str(ticket_id),
    )
    await session.commit()
    await state.clear()

    await message.answer(
        "پیام شما ثبت شد.",
        reply_markup=support_ticket_keyboard(ticket_id, is_closed=False),
    )

    for owner_id in get_settings().telegram_owner_ids:
        try:
            await bot.send_message(
                owner_id,
                "<b>پیام جدید پشتیبانی</b>\n"
                f"تیکت: <code>{ticket_id}</code>\n"
                f"مشتری: <code>{customer.telegram_user_id}</code>\n\n"
                f"{escape(support_message.body)}",
            )
        except TelegramAPIError:
            continue


@router.callback_query(F.data.startswith("support:close:"))
async def support_close(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    try:
        ticket_id = UUID(
            hex=(callback.data or "").removeprefix("support:close:")
        )
    except ValueError:
        await callback.answer("شناسه تیکت معتبر نیست.", show_alert=True)
        return

    customer = await _customer(
        session,
        telegram_user_id=callback.from_user.id,
    )
    if customer is None:
        await callback.answer("حساب کاربری پیدا نشد.", show_alert=True)
        return

    try:
        ticket = await close_ticket(
            session,
            customer_id=customer.id,
            ticket_id=ticket_id,
        )
    except SupportStateError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await record_audit_event(
        session,
        actor_type="customer",
        actor_id=str(customer.telegram_user_id),
        action="support.customer_closed",
        entity_type="support_ticket",
        entity_id=str(ticket.id),
        correlation_id=str(ticket.id),
    )
    await session.commit()
    await callback.answer("تیکت بسته شد.")
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "تیکت بسته شد.",
            reply_markup=main_menu(),
        )
