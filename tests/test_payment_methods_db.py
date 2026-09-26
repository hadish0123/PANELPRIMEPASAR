from uuid import uuid4

import pytest

from panelprimepasar.config import Settings
from panelprimepasar.db import SessionFactory
from panelprimepasar.models import PaymentMethodKind
from panelprimepasar.security.payment_secrets import (
    decrypt_payment_secrets,
    encrypt_payment_secrets,
)
from panelprimepasar.services.payment_methods import (
    PaymentMethodInput,
    PaymentMethodStateError,
    configure_payment_method,
    decrypt_method_credentials,
    list_enabled_payment_methods,
    payment_method_public_view,
)


def test_payment_credentials_roundtrip() -> None:
    key = "this-is-a-long-test-master-key-123456789"
    encrypted = encrypt_payment_secrets(
        {"merchant_id": "secret-merchant"},
        master_key=key,
    )

    assert "secret-merchant" not in encrypted
    assert decrypt_payment_secrets(
        encrypted,
        master_key=key,
    ) == {"merchant_id": "secret-merchant"}


@pytest.mark.asyncio(loop_scope="session")
async def test_configured_gateway_secrets_are_encrypted_and_hidden() -> None:
    marker = uuid4().hex
    settings = Settings(
        payment_callback_base_url="https://payments.example.test",
        payment_credentials_master_key="master-key-for-payment-tests-123456789",
    )

    async with SessionFactory() as session:
        method = await configure_payment_method(
            session,
            settings=settings,
            values=PaymentMethodInput(
                slug=f"zp{marker[:8]}",
                kind=PaymentMethodKind.ZARINPAL,
                display_name="زرین پال تست",
                is_enabled=True,
                sandbox=True,
                sort_order=10,
                public_config={},
                credentials={"merchant_id": "merchant-private-value"},
            ),
        )

        assert method.secret_config_encrypted is not None
        assert "merchant-private-value" not in method.secret_config_encrypted
        assert decrypt_method_credentials(
            method,
            settings=settings,
        ) == {"merchant_id": "merchant-private-value"}

        public = payment_method_public_view(method)
        assert public["credentials_configured"] is True
        assert "merchant-private-value" not in str(public)

        enabled = await list_enabled_payment_methods(session)
        assert method.id in {item.id for item in enabled}
        await session.rollback()


@pytest.mark.asyncio(loop_scope="session")
async def test_manual_card_method_does_not_store_secret_credentials() -> None:
    marker = uuid4().hex
    settings = Settings()

    async with SessionFactory() as session:
        method = await configure_payment_method(
            session,
            settings=settings,
            values=PaymentMethodInput(
                slug=f"card{marker[:8]}",
                kind=PaymentMethodKind.MANUAL_CARD,
                display_name="کارت به کارت",
                is_enabled=True,
                sandbox=False,
                sort_order=0,
                public_config={
                    "card_number": "6037-9912-3456-7890",
                    "card_holder": "Test Owner",
                    "bank_name": "Test Bank",
                },
                credentials=None,
            ),
        )

        assert method.secret_config_encrypted is None
        public = payment_method_public_view(method)
        config = public["public_config"]
        assert isinstance(config, dict)
        assert config["card_number"] == "6037991234567890"
        assert config["card_holder"] == "Test Owner"
        await session.rollback()



@pytest.mark.asyncio(loop_scope="session")
async def test_existing_gateway_credentials_are_revalidated_on_update() -> None:
    marker = uuid4().hex
    settings = Settings(
        payment_callback_base_url="https://payments.example.test",
        payment_credentials_master_key="master-key-for-payment-tests-123456789",
    )

    async with SessionFactory() as session:
        method = await configure_payment_method(
            session,
            settings=settings,
            values=PaymentMethodInput(
                slug=f"zb{marker[:8]}",
                kind=PaymentMethodKind.ZIBAL,
                display_name="زیبال تست",
                is_enabled=False,
                sandbox=True,
                sort_order=0,
                public_config={},
                credentials={},
            ),
        )

        with pytest.raises(PaymentMethodStateError):
            await configure_payment_method(
                session,
                settings=settings,
                method_id=method.id,
                values=PaymentMethodInput(
                    slug=method.slug,
                    kind=PaymentMethodKind.ZIBAL,
                    display_name=method.display_name,
                    is_enabled=True,
                    sandbox=False,
                    sort_order=method.sort_order,
                    public_config={},
                    credentials=None,
                ),
            )
        await session.rollback()
