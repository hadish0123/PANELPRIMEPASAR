from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import Message

from panelprimepasar.services.telegram_history import clear_recent_private_history


async def test_start_cleanup_deletes_recent_private_history_in_batches() -> None:
    delete_messages = AsyncMock()
    bot = cast(Bot, cast(Any, SimpleNamespace(delete_messages=delete_messages)))
    message = cast(
        Message,
        cast(
            Any,
            SimpleNamespace(
                chat=SimpleNamespace(id=12345, type=ChatType.PRIVATE),
                message_id=205,
            ),
        ),
    )

    await clear_recent_private_history(bot, message)

    assert delete_messages.await_count == 3
    deleted_ids = [
        message_id
        for call in delete_messages.await_args_list
        for message_id in call.kwargs["message_ids"]
    ]
    assert deleted_ids == list(range(1, 205))
    assert 205 not in deleted_ids


async def test_first_start_message_is_kept() -> None:
    delete_messages = AsyncMock()
    bot = cast(Bot, cast(Any, SimpleNamespace(delete_messages=delete_messages)))
    message = cast(
        Message,
        cast(
            Any,
            SimpleNamespace(
                chat=SimpleNamespace(id=12345, type=ChatType.PRIVATE),
                message_id=1,
            ),
        ),
    )

    await clear_recent_private_history(bot, message)

    delete_messages.assert_not_awaited()


async def test_start_cleanup_does_not_delete_group_history() -> None:
    delete_messages = AsyncMock()
    bot = cast(Bot, cast(Any, SimpleNamespace(delete_messages=delete_messages)))
    message = cast(
        Message,
        cast(
            Any,
            SimpleNamespace(
                chat=SimpleNamespace(id=-100123, type=ChatType.SUPERGROUP),
                message_id=20,
            ),
        ),
    )

    await clear_recent_private_history(bot, message)

    delete_messages.assert_not_awaited()
