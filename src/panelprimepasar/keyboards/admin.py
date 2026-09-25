from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import Plan


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ پلن جدید", callback_data="admin:create_plan")
    builder.button(text="📋 مدیریت پلن‌ها", callback_data="admin:plans")
    builder.button(text="🧾 سفارش‌های اخیر", callback_data="admin:orders")
    builder.adjust(1)
    return builder.as_markup()


def admin_plans_keyboard(plans: Sequence[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        state = "🟢" if plan.is_active else "⚪️"
        builder.button(
            text=f"{state} {plan.name}",
            callback_data=f"admin:toggle_plan:{plan.id}",
        )
    builder.button(text="➕ پلن جدید", callback_data="admin:create_plan")
    builder.button(text="↩️ منوی مدیریت", callback_data="admin:home")
    builder.adjust(1)
    return builder.as_markup()
