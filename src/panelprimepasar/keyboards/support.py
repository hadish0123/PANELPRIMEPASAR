from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import SupportTicket, TicketStatus


def support_home_keyboard(
    tickets: Sequence[SupportTicket],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ تیکت جدید", callback_data="support:new")
    for ticket in tickets:
        icon = "✅" if ticket.status == TicketStatus.CLOSED.value else "🎫"
        builder.button(
            text=f"{icon} {ticket.subject[:24]}",
            callback_data=f"support:ticket:{ticket.id.hex}",
        )
    builder.adjust(1)
    return builder.as_markup()


def support_ticket_keyboard(
    ticket_id: UUID,
    *,
    is_closed: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not is_closed:
        builder.button(
            text="✍️ پاسخ",
            callback_data=f"support:reply:{ticket_id.hex}",
        )
        builder.button(
            text="✅ بستن تیکت",
            callback_data=f"support:close:{ticket_id.hex}",
        )
    builder.button(text="↩️ پشتیبانی", callback_data="support:home")
    builder.adjust(1)
    return builder.as_markup()
