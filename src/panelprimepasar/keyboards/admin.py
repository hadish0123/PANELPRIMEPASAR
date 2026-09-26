from collections.abc import Sequence
from uuid import UUID

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from panelprimepasar.models import Order, OrderStatus, Plan


def admin_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 داشبورد", callback_data="admin:dashboard")
    builder.button(text="👥 مشتریان", callback_data="admin:customers")
    builder.button(text="🧾 سفارش‌ها", callback_data="admin:orders")
    builder.button(text="💳 پرداخت‌ها", callback_data="admin:payments")
    builder.button(text="📋 پلن‌ها", callback_data="admin:plans")
    builder.button(text="➕ پلن جدید", callback_data="admin:create_plan")
    builder.button(text="🎧 پشتیبانی", callback_data="admin:support")
    builder.button(text="👮 مدیران", callback_data="admin:staff")
    builder.button(text="🔌 پاسارگارد", callback_data="admin:pasarguard_check")
    builder.button(text="📜 لاگ‌ها", callback_data="admin:audit")
    builder.adjust(2, 2, 2, 2, 2)
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


def admin_orders_keyboard(orders: Sequence[Order]) -> InlineKeyboardMarkup:
    status_icon = {
        OrderStatus.PENDING: "⏳",
        OrderStatus.AWAITING_PAYMENT: "💳",
        OrderStatus.PAID: "✅",
        OrderStatus.PROVISIONING: "⚙️",
        OrderStatus.COMPLETED: "🟢",
        OrderStatus.FAILED: "🔴",
        OrderStatus.CANCELED: "⚪️",
    }

    builder = InlineKeyboardBuilder()
    for order in orders:
        builder.button(
            text=(
                f"{status_icon[order.status]} "
                f"{str(order.id)[:8]} · {order.price_amount:,} {order.currency}"
            ),
            callback_data=f"admin:order:{order.id}",
        )
    builder.button(text="↩️ منوی مدیریت", callback_data="admin:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_order_actions_keyboard(order: Order) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if order.status in {OrderStatus.PENDING, OrderStatus.AWAITING_PAYMENT}:
        builder.button(
            text="✅ تأیید پرداخت و اجرای سفارش",
            callback_data=f"admin:approve:{order.id}",
        )
        builder.button(
            text="❌ رد رسید پرداخت",
            callback_data=f"admin:reject_payment:{order.id}",
        )
        builder.button(
            text="🗑 لغو سفارش",
            callback_data=f"admin:cancel_order:{order.id}",
        )
    elif order.status in {OrderStatus.PAID, OrderStatus.PROVISIONING, OrderStatus.FAILED}:
        builder.button(
            text="🔄 ساخت / تلاش مجدد پنل",
            callback_data=f"admin:provision:{order.id}",
        )
    elif order.status == OrderStatus.COMPLETED:
        builder.button(
            text="🔐 صدور مجدد رمز و ارسال",
            callback_data=f"admin:reissue:{order.id}",
        )

    builder.button(text="↩️ سفارش‌ها", callback_data="admin:orders")
    builder.adjust(1)
    return builder.as_markup()


def admin_order_notification_keyboard(order_id: UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🧾 مشاهده و بررسی سفارش",
        callback_data=f"admin:order:{order_id}",
    )
    return builder.as_markup()
