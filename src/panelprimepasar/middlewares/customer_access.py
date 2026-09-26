from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.models import Customer


class CustomerAccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if not isinstance(session, AsyncSession) or user is None:
            return await handler(event, data)

        customer = await session.scalar(
            select(Customer).where(Customer.telegram_user_id == user.id)
        )
        if customer is None or not customer.is_blocked:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer(
                "دسترسی این حساب توسط مدیریت مسدود شده است.",
                show_alert=True,
            )
        elif isinstance(event, Message):
            await event.answer("دسترسی این حساب توسط مدیریت مسدود شده است.")
        return None
