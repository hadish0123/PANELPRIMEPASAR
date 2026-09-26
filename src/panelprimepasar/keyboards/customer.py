from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import Plan, Subscription


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🛒 خرید پنل"),
                KeyboardButton(text="📡 سرویس‌های من"),
            ],
            [
                KeyboardButton(text="📦 سفارش‌های من"),
                KeyboardButton(text="👤 حساب من"),
            ],
            [
                KeyboardButton(text="🎧 پشتیبانی"),
                KeyboardButton(text="ℹ️ راهنما"),
            ],
        ],
        resize_keyboard=True,
    )


def plans_keyboard(plans: Sequence[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(text=plan.name, callback_data=f"plan:{plan.id}")
    builder.adjust(1)
    return builder.as_markup()


def plan_actions_keyboard(plan_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ ثبت سفارش", callback_data=f"checkout:{plan_id}")
    builder.button(text="↩️ پلن‌ها", callback_data="catalog")
    builder.adjust(1)
    return builder.as_markup()


def payment_receipt_keyboard(order_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📎 ارسال رسید پرداخت", callback_data=f"receipt:{order_id}")
    builder.button(text="🛒 مشاهده پلن‌ها", callback_data="catalog")
    builder.adjust(1)
    return builder.as_markup()


def subscriptions_keyboard(
    subscriptions: Sequence[Subscription],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subscription in subscriptions:
        builder.button(
            text=f"📡 {str(subscription.id)[:8]} · {subscription.status}",
            callback_data=f"service:{subscription.id}",
        )
    builder.adjust(1)
    return builder.as_markup()


def subscription_actions_keyboard(subscription_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 تمدید سرویس",
        callback_data=f"service_renew:{subscription_id}",
    )
    builder.button(
        text="➕ افزایش حجم",
        callback_data=f"service_topup:{subscription_id}",
    )
    builder.button(text="↩️ سرویس‌های من", callback_data="services")
    builder.adjust(2, 1)
    return builder.as_markup()


def lifecycle_plans_keyboard(
    plans: Sequence[Plan],
    *,
    subscription_id: UUID,
    action: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=plan.name,
            callback_data=f"{action}_plan:{subscription_id}:{plan.id}",
        )
    builder.button(text="↩️ سرویس", callback_data=f"service:{subscription_id}")
    builder.adjust(1)
    return builder.as_markup()
