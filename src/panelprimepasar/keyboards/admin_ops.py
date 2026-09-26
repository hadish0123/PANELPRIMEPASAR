from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import StaffAdmin, SupportTicket


def admin_full_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 داشبورد", callback_data="admin:dashboard")
    builder.button(text="👥 مشتریان", callback_data="admin:customers")
    builder.button(text="🧾 سفارش‌ها", callback_data="admin:orders")
    builder.button(text="💳 پرداخت‌ها", callback_data="admin:payments")
    builder.button(text="📦 پلن‌ها", callback_data="admin:plans")
    builder.button(text="🎧 پشتیبانی", callback_data="admin:support")
    builder.button(text="👮 مدیران", callback_data="admin:staff")
    builder.button(text="🔌 پاسارگارد", callback_data="admin:pasarguard_check")
    builder.button(text="📜 لاگ‌ها", callback_data="admin:audit")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def support_tickets_keyboard(
    tickets: Sequence[SupportTicket],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ticket in tickets:
        builder.button(
            text=f"🎫 {str(ticket.id)[:8]} · {ticket.status}",
            callback_data=f"admin:ticket:{ticket.id.hex}",
        )
    builder.button(text="↩️ منوی مدیریت", callback_data="admin:home")
    builder.adjust(1)
    return builder.as_markup()


def support_ticket_actions_keyboard(ticket_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✍️ پاسخ",
        callback_data=f"admin:ticket_reply:{ticket_id.hex}",
    )
    builder.button(
        text="✅ بستن تیکت",
        callback_data=f"admin:ticket_close:{ticket_id.hex}",
    )
    builder.button(text="↩️ تیکت‌ها", callback_data="admin:support")
    builder.adjust(1)
    return builder.as_markup()


def staff_admins_keyboard(staff: Sequence[StaffAdmin]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for admin in staff:
        state = "🟢" if admin.is_active else "⚪️"
        label = admin.telegram_user_id if admin.telegram_user_id is not None else "web"
        builder.button(
            text=f"{state} {label} · {admin.role}",
            callback_data=f"admin:staff_toggle:{admin.id.hex}",
        )
    builder.button(text="➕ افزودن مدیر", callback_data="admin:staff_add")
    builder.button(text="↩️ منوی مدیریت", callback_data="admin:home")
    builder.adjust(1)
    return builder.as_markup()


def staff_role_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for role in ("admin", "sales", "finance", "support"):
        builder.button(
            text=role,
            callback_data=f"admin:staff_role:{role}",
        )
    builder.button(text="❌ لغو", callback_data="admin:home")
    builder.adjust(2)
    return builder.as_markup()
