from html import escape
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import get_settings
from panelprimepasar.keyboards.admin import admin_menu, admin_plans_keyboard
from panelprimepasar.models import Order, Plan
from panelprimepasar.routers.customer import format_money, format_quota, order_status_label
from panelprimepasar.services.plan_inputs import (
    parse_price_toman,
    parse_quota,
    parse_validity_days,
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
        "اعتبار پلن را به روز وارد کنید. برای بدون محدودیت زمانی عدد <code>0</code> بفرستید."
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
    await state.clear()

    validity_text = f"{validity_days} روز" if validity_days is not None else "بدون محدودیت"
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
        await callback.message.answer("هنوز پلنی ساخته نشده است.", reply_markup=admin_menu())
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

    data = callback.data or ""
    try:
        plan_id = UUID(data.removeprefix("admin:toggle_plan:"))
    except ValueError:
        await callback.answer("شناسه پلن معتبر نیست.", show_alert=True)
        return

    plan = await session.scalar(select(Plan).where(Plan.id == plan_id))
    if plan is None:
        await callback.answer("پلن پیدا نشد.", show_alert=True)
        return

    plan.is_active = not plan.is_active
    await session.flush()
    await callback.answer("وضعیت پلن تغییر کرد.")

    plans = list(
        (
            await session.scalars(
                select(Plan).order_by(Plan.sort_order.asc(), Plan.created_at.desc())
            )
        ).all()
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=admin_plans_keyboard(plans))


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
        await callback.message.answer("هنوز سفارشی ثبت نشده است.", reply_markup=admin_menu())
        return

    rows = [
        (
            f"<code>{order.id}</code> — "
            f"{format_money(order.price_amount, order.currency)} — "
            f"{order_status_label(order.status)}"
        )
        for order in orders
    ]
    await callback.message.answer(
        "<b>20 سفارش اخیر</b>\n\n" + "\n".join(rows),
        reply_markup=admin_menu(),
    )
