from uuid import uuid4

import pytest
from starlette.requests import Request

from panelprimepasar.db import SessionFactory
from panelprimepasar.models import (
    Customer,
    Order,
    OrderStatus,
    Payment,
    PaymentMethodConfig,
    PaymentStatus,
    Plan,
)
from panelprimepasar.payment_callbacks import payment_callback


@pytest.mark.asyncio(loop_scope="session")
async def test_canceled_zarinpal_callback_keeps_payment_retryable() -> None:
    marker = uuid4().hex

    async with SessionFactory() as session:
        customer = Customer(
            telegram_user_id=int(marker[:15], 16),
            telegram_username=f"callback_{marker[:8]}",
            first_name="Callback",
            last_name=None,
        )
        plan = Plan(
            name=f"callback-plan-{marker}",
            quota_bytes=100_000_000_000,
            price_amount=100_000,
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
            secret_config_encrypted="encrypted-placeholder",
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
            idempotency_key=f"callback:{marker}",
        )
        session.add(order)
        await session.flush()

        payment = Payment(
            order_id=order.id,
            payment_method_id=method.id,
            provider="zarinpal",
            provider_reference="AUTH-CANCELED",
            payment_url="https://payment.zarinpal.com/pg/StartPay/AUTH-CANCELED",
            amount=order.price_amount,
            currency=order.currency,
            status=PaymentStatus.PENDING,
        )
        session.add(payment)
        await session.flush()

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": f"/payments/callback/{payment.id}",
                "query_string": b"Status=NOK&Authority=AUTH-CANCELED",
                "headers": [],
                "app": None,
            }
        )
        response = await payment_callback(
            payment_id=payment.id,
            request=request,
            session=session,
        )

        await session.refresh(payment)
        await session.refresh(order)
        assert response.status_code == 400
        assert payment.status == PaymentStatus.PENDING
        assert order.status == OrderStatus.AWAITING_PAYMENT
        await session.rollback()
