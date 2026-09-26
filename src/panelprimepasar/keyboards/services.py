from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import Plan, Subscription


def subscriptions_keyboard(
    subscriptions: Sequence[Subscription],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subscription in subscriptions:
        builder.button(
            text=f"📦 {str(subscription.id)[:8]} · {subscription.status}",
            callback_data=f"svc:{subscription.id.hex}",
        )
    builder.adjust(1)
    return builder.as_markup()


def subscription_actions_keyboard(subscription_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🔄 تمدید سرویس",
        callback_data=f"svc_renew:{subscription_id.hex}",
    )
    builder.button(
        text="➕ افزایش حجم",
        callback_data=f"svc_topup:{subscription_id.hex}",
    )
    builder.button(text="↩️ سرویس‌های من", callback_data="svc_list")
    builder.adjust(1)
    return builder.as_markup()


def subscription_picker_keyboard(
    subscriptions: Sequence[Subscription],
    *,
    action: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subscription in subscriptions:
        builder.button(
            text=f"📦 {str(subscription.id)[:8]}",
            callback_data=f"svcact:{action}:{subscription.id.hex}",
        )
    builder.adjust(1)
    return builder.as_markup()


def lifecycle_plans_keyboard(plans: Sequence[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=plan.name,
            callback_data=f"lifeplan:{plan.id.hex}",
        )
    builder.button(text="❌ لغو", callback_data="life_cancel")
    builder.adjust(1)
    return builder.as_markup()
