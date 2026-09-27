from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from panelprimepasar.config import Settings
from panelprimepasar.routers import admin as admin_router
from panelprimepasar.services.provisioning import (
    ProvisionedCredentials,
    ProvisioningOutcome,
)


async def test_admin_delivery_uses_customer_dashboard_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id = UUID("11111111-1111-1111-1111-111111111111")
    settings = Settings()
    session = cast(Any, SimpleNamespace())
    customer = cast(Any, SimpleNamespace(telegram_user_id=12345))
    bot = cast(Any, SimpleNamespace(send_message=AsyncMock()))
    resolve_panel_url = AsyncMock(return_value="https://pasarguard.example/dashboard")
    monkeypatch.setattr(
        admin_router,
        "resolve_order_panel_url",
        resolve_panel_url,
    )

    delivered = await admin_router._deliver_credentials(
        bot=bot,
        session=session,
        settings=settings,
        customer=customer,
        order_id=order_id,
        outcome=ProvisioningOutcome(
            success=True,
            credentials=ProvisionedCredentials(
                username="customer",
                password="secret",
                admin_id=7,
                role_id=3,
                role_name="reseller",
            ),
        ),
    )

    assert delivered is True
    resolve_panel_url.assert_awaited_once_with(
        session,
        settings=settings,
        order_id=order_id,
    )
    bot.send_message.assert_awaited_once()
    assert "https://pasarguard.example/dashboard" in bot.send_message.await_args.args[1]
