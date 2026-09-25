import asyncio

from panelprimepasar.bot import build_bot, build_dispatcher
from panelprimepasar.config import get_settings


async def main() -> None:
    settings = get_settings()
    bot = build_bot(settings)
    dispatcher = build_dispatcher()

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
