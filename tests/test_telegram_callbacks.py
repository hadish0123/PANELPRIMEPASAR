from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery
from aiogram.types import CallbackQuery, Message

from panelprimepasar.routers import customer as customer_router
from panelprimepasar.services.telegram_callbacks import answer_callback


def _telegram_bad_request(message: str) -> TelegramBadRequest:
    return TelegramBadRequest(
        method=AnswerCallbackQuery(callback_query_id="callback-id"),
        message=message,
    )


def _callback(answer: AsyncMock) -> CallbackQuery:
    return cast(CallbackQuery, cast(Any, SimpleNamespace(answer=answer)))


async def test_answer_callback_succeeds_normally() -> None:
    answer = AsyncMock()

    acknowledged = await answer_callback(
        _callback(answer),
        "انجام شد.",
        show_alert=True,
    )

    assert acknowledged is True
    answer.assert_awaited_once_with(text="انجام شد.", show_alert=True)


async def test_answer_callback_ignores_expired_query() -> None:
    answer = AsyncMock(
        side_effect=_telegram_bad_request(
            "Bad Request: query is too old and response timeout expired or query ID is invalid"
        )
    )

    acknowledged = await answer_callback(_callback(answer))

    assert acknowledged is False


async def test_answer_callback_reraises_other_telegram_errors() -> None:
    error = _telegram_bad_request("Bad Request: unexpected callback error")
    answer = AsyncMock(side_effect=error)

    with pytest.raises(TelegramBadRequest) as raised:
        await answer_callback(_callback(answer))

    assert raised.value is error


async def test_plan_button_continues_after_expired_acknowledgement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan_id = UUID("11111111-1111-1111-1111-111111111111")
    plan = SimpleNamespace(
        id=plan_id,
        name="پلن تست",
        quota_bytes=50_000_000_000,
        price_amount=100_000,
        currency="IRT",
    )
    answer = AsyncMock(
        side_effect=_telegram_bad_request(
            "Bad Request: query is too old and response timeout expired"
        )
    )
    callback = _callback(answer)
    callback.data = f"plan:{plan_id}"
    message = MagicMock(spec=Message)
    message.edit_text = AsyncMock()
    callback.message = message
    get_active_plan = AsyncMock(return_value=plan)
    monkeypatch.setattr(customer_router, "get_active_plan", get_active_plan)

    await customer_router.plan_details(callback, cast(Any, SimpleNamespace()))

    message.edit_text.assert_awaited_once()
    assert "پلن تست" in message.edit_text.await_args.args[0]
