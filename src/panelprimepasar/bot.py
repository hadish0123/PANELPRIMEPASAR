from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from panelprimepasar.config import Settings
from panelprimepasar.db import SessionFactory
from panelprimepasar.middlewares.database import DatabaseSessionMiddleware
from panelprimepasar.routers import customer_router


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware(SessionFactory))
    dispatcher.include_router(customer_router)
    return dispatcher


def build_bot(settings: Settings) -> Bot:
    if settings.telegram_bot_token is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot")

    return Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
