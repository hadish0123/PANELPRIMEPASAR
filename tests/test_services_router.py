from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from aiogram.types import CallbackQuery, Message

from panelprimepasar.models import OrderKind
from panelprimepasar.routers import services as services_router


async def test_service_list_callback_uses_customer_id_not_bot_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    customer = SimpleNamespace(id=UUID("11111111-1111-1111-1111-111111111111"))
    customer_for_user = AsyncMock(return_value=customer)
    list_subscriptions = AsyncMock(return_value=[])
    monkeypatch.setattr(services_router, "_customer_for_user", customer_for_user)
    monkeypatch.setattr(
        services_router,
        "list_customer_subscriptions",
        list_subscriptions,
    )
    message = MagicMock(spec=Message)
    message.from_user = SimpleNamespace(id=999999)
    message.answer = AsyncMock()
    session = cast(Any, SimpleNamespace())

    await services_router._send_subscription_list(
        message,
        session,
        telegram_user_id=12345,
    )

    customer_for_user.assert_awaited_once_with(session, 12345)
    list_subscriptions.assert_awaited_once_with(
        session,
        customer_id=customer.id,
    )


@pytest.mark.parametrize("kind", [OrderKind.RENEWAL, OrderKind.TOPUP])
async def test_lifecycle_plan_button_creates_order_and_sends_payment_step(
    monkeypatch: pytest.MonkeyPatch,
    kind: OrderKind,
) -> None:
    customer = SimpleNamespace(id=UUID("11111111-1111-1111-1111-111111111111"))
    subscription = SimpleNamespace(id=UUID("22222222-2222-2222-2222-222222222222"))
    plan = SimpleNamespace(id=UUID("33333333-3333-3333-3333-333333333333"))
    order = SimpleNamespace(
        id=UUID("44444444-4444-4444-4444-444444444444"),
        price_amount=150_000,
        currency="IRT",
    )
    monkeypatch.setattr(
        services_router,
        "_customer_for_user",
        AsyncMock(return_value=customer),
    )
    monkeypatch.setattr(
        services_router,
        "get_customer_subscription",
        AsyncMock(return_value=subscription),
    )
    create_order = AsyncMock(return_value=(order, True))
    monkeypatch.setattr(services_router, "create_lifecycle_order", create_order)
    monkeypatch.setattr(
        services_router,
        "list_enabled_payment_methods",
        AsyncMock(return_value=[]),
    )
    callback = cast(
        CallbackQuery,
        cast(
            Any,
            SimpleNamespace(
                id="callback-id",
                data=f"lifeplan:{plan.id.hex}",
                from_user=SimpleNamespace(id=12345),
                message=MagicMock(spec=Message, message_id=77),
                answer=AsyncMock(),
            ),
        ),
    )
    bot = cast(Any, SimpleNamespace(send_message=AsyncMock()))
    state = cast(
        Any,
        SimpleNamespace(
            get_data=AsyncMock(
                return_value={
                    "subscription_id": str(subscription.id),
                    "order_kind": kind.value,
                }
            ),
            clear=AsyncMock(),
        ),
    )
    session = cast(Any, SimpleNamespace(scalar=AsyncMock(return_value=plan)))

    await services_router.lifecycle_plan_selected(callback, bot, state, session)

    create_order.assert_awaited_once()
    assert create_order.await_args.kwargs["kind"] == kind
    bot.send_message.assert_awaited_once()
    expected_action = "تمدید" if kind == OrderKind.RENEWAL else "افزایش حجم"
    assert expected_action in bot.send_message.await_args.kwargs["text"]
