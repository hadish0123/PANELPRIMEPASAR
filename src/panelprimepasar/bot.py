from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from panelprimepasar.config import Settings
from panelprimepasar.db import SessionFactory
from panelprimepasar.middlewares.customer_access import CustomerAccessMiddleware
from panelprimepasar.middlewares.database import DatabaseSessionMiddleware
from panelprimepasar.routers import (
    admin_ops_router,
    admin_router,
    customer_router,
    services_router,
    support_router,
)


def build_dispatcher(settings: Settings) -> Dispatcher:
    storage = RedisStorage.from_url(
        settings.redis_url,
        state_ttl=3600,
        data_ttl=3600,
    )
    dispatcher = Dispatcher(storage=storage)
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware(SessionFactory))

    customer_access = CustomerAccessMiddleware()
    for customer_scope in (customer_router, services_router, support_router):
        customer_scope.message.outer_middleware(customer_access)
        customer_scope.callback_query.outer_middleware(customer_access)

    dispatcher.include_router(admin_router)
    dispatcher.include_router(admin_ops_router)
    dispatcher.include_router(customer_router)
    dispatcher.include_router(services_router)
    dispatcher.include_router(support_router)
    return dispatcher


def build_bot(settings: Settings) -> Bot:
    if settings.telegram_bot_token is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot")

    return Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
