from uuid import uuid4

import pytest

from panelprimepasar.config import Settings
from panelprimepasar.db import SessionFactory
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    PaymentMethodConfig,
    PaymentStatus,
    Plan,
)
from panelprimepasar.payments.base import (
    ExternalPaymentStatus,
    PaymentIntent,
    PaymentVerification,
)
from panelprimepasar.services import payment_methods as payment_methods_service
from panelprimepasar.services.payment_methods import (
    start_external_payment,
    verify_external_payment,
)


class FakeGateway:
    name = "zarinpal"

    def __init__(self) -> None:
        self.create_calls = 0
        self.verify_calls = 0
        self.close_calls = 0

    async def create_intent(
        self,
        *,
        order_id,
        amount,
        currency,
        callback_url,
        description,
    ) -> PaymentIntent:
        del order_id, callback_url, description
        self.create_calls += 1
        return PaymentIntent(
            provider=self.name,
            reference="AUTH-IDEMPOTENT",
            amount=amount,
            currency=currency,
            status=ExternalPaymentStatus.PENDING,
            payment_url="https://gateway.example/pay/AUTH-IDEMPOTENT",
        )

    async def verify(
        self,
        *,
        order_id,
        reference,
        amount,
        currency,
    ) -> PaymentVerification:
        del order_id
        self.verify_calls += 1
        return PaymentVerification(
            provider=self.name,
            reference=reference,
            transaction_id="REF-IDEMPOTENT",
            amount=amount,
            currency=currency,
            status=ExternalPaymentStatus.PAID,
        )

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio(loop_scope="session")
async def test_external_payment_start_and_verify_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = uuid4().hex
    gateway = FakeGateway()
    monkeypatch.setattr(
        payment_methods_service,
        "build_payment_provider",
        lambda method, settings: gateway,
    )
    settings = Settings(
        payment_callback_base_url="https://payments.example.test",
    )

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"gateway_{marker[:8]}",
            first_name="Gateway",
            last_name=None,
        )
        plan = Plan(
            name=f"gateway-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=120_000,
            currency="IRT",
            validity_days=30,
            is_active=True,
            sort_order=0,
        )
        method = PaymentMethodConfig(
            slug=f"zp{marker[:8]}",
            kind="zarinpal",
            display_name="زرین پال",
            is_enabled=True,
            sandbox=False,
            sort_order=0,
            public_config_json="{}",
            secret_config_encrypted="test-encrypted-value",
        )
        session.add_all([customer, plan, method])
        await session.flush()

        order = Order(
            customer_id=customer.id,
            plan_id=plan.id,
            status=OrderStatus.AWAITING_PAYMENT,
            price_amount=plan.price_amount,
            currency=plan.currency,
            quota_bytes=plan.quota_bytes,
            validity_days=plan.validity_days,
            idempotency_key=f"gateway:{marker}",
        )
        session.add(order)
        await session.flush()

        first_payment, first_intent = await start_external_payment(
            session,
            settings=settings,
            order=order,
            method=method,
        )
        second_payment, second_intent = await start_external_payment(
            session,
            settings=settings,
            order=order,
            method=method,
        )

        assert first_payment.id == second_payment.id
        assert first_intent.reference == second_intent.reference
        assert gateway.create_calls == 1

        first_verified = await verify_external_payment(
            session,
            settings=settings,
            payment=first_payment,
            method=method,
        )
        second_verified = await verify_external_payment(
            session,
            settings=settings,
            payment=first_payment,
            method=method,
        )

        assert first_verified.id == second_verified.id
        assert first_verified.status == PaymentStatus.VERIFIED
        assert first_verified.provider_transaction_id == "zarinpal:REF-IDEMPOTENT"
        assert order.status == OrderStatus.PAID
        assert gateway.verify_calls == 1
        await session.rollback()
