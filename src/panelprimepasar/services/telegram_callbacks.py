from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

_EXPIRED_QUERY_MESSAGES = (
    "query is too old",
    "response timeout expired",
    "query id is invalid",
)


async def answer_callback(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool | None = None,
) -> bool:
    """Answer a callback without aborting its handler when Telegram expired it."""
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        error_message = str(exc).casefold()
        if any(fragment in error_message for fragment in _EXPIRED_QUERY_MESSAGES):
            return False
        raise
    return True
