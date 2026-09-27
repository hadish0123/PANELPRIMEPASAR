from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

_DELETE_BATCH_SIZE = 100
_MAX_RECENT_MESSAGES = 1_000


async def clear_recent_private_history(bot: Bot, message: Message) -> None:
    """Best-effort cleanup of deletable private-chat history, including /start."""
    if message.chat.type != ChatType.PRIVATE or message.message_id < 1:
        return

    first_message_id = max(1, message.message_id - _MAX_RECENT_MESSAGES + 1)
    message_ids = list(range(first_message_id, message.message_id + 1))
    for offset in range(0, len(message_ids), _DELETE_BATCH_SIZE):
        batch = message_ids[offset : offset + _DELETE_BATCH_SIZE]
        try:
            await bot.delete_messages(chat_id=message.chat.id, message_ids=batch)
        except TelegramAPIError:
            # Telegram can reject messages outside its deletion window. Starting
            # the new session is more important than failing the entire command.
            continue
