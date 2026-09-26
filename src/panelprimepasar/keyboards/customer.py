from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import Plan


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 خرید پنل"),
                KeyboardButton(text="📦 سرویس‌های من"),
            ],
            [
                KeyboardButton(text="🔄 تمدید سرویس"),
                KeyboardButton(text="➕ افزایش حجم"),
            ],
            [
                KeyboardButton(text="📜 سفارش‌های من"),
                KeyboardButton(text="👤 حساب من"),
            ],
            [
                KeyboardButton(text="💰 کیف پول"),
                KeyboardButton(text="🎧 پشتیبانی"),
            ],
        ],
        resize_keyboard=True,
    )


def plans_keyboard(plans: Sequence[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=plan.name,
            callback_data=f"plan:{plan.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def plan_actions_keyboard(plan_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ ثبت سفارش",
        callback_data=f"checkout:{plan_id}",
    )
    builder.button(text="↩️ پلن‌ها", callback_data="catalog")
    builder.adjust(1)
    return builder.as_markup()


def payment_receipt_keyboard(order_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="💰 پرداخت از کیف پول",
        callback_data=f"wallet_pay:{order_id}",
    )
    builder.button(
        text="🎟 کد تخفیف",
        callback_data=f"discount:{order_id}",
    )
    builder.button(
        text="📎 ارسال رسید پرداخت",
        callback_data=f"receipt:{order_id}",
    )
    builder.button(text="🛒 مشاهده پلن‌ها", callback_data="catalog")
    builder.adjust(1)
    return builder.as_markup()
