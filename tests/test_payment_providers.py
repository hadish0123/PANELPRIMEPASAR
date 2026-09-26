from uuid import uuid4

import httpx
import pytest

from panelprimepasar.payments.base import ExternalPaymentStatus
from panelprimepasar.payments.providers import (
    IDPayProvider,
    NextPayProvider,
    ZarinPalProvider,
    ZibalProvider,
)


@pytest.mark.asyncio
async def test_zarinpal_request_and_verify_convert_toman_to_rial() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/request.json"):
            payload = __import__("json").loads(request.content)
            assert payload["amount"] == 1_250_000
            return httpx.Response(
                200,
                json={"data": {"code": 100, "authority": "AUTH-1"}, "errors": []},
            )
        if request.url.path.endswith("/verify.json"):
            payload = __import__("json").loads(request.content)
            assert payload["amount"] == 1_250_000
            assert payload["authority"] == "AUTH-1"
            return httpx.Response(
                200,
                json={"data": {"code": 100, "ref_id": 998877}, "errors": []},
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ZarinPalProvider(
        merchant_id="merchant-test",
        sandbox=False,
        timeout_seconds=5,
        client=client,
    )
    order_id = uuid4()
    try:
        intent = await provider.create_intent(
            order_id=order_id,
            amount=125_000,
            currency="IRT",
            callback_url="https://example.test/payments/callback/1",
            description="test order",
        )
        assert intent.reference == "AUTH-1"
        assert intent.payment_url == "https://payment.zarinpal.com/pg/StartPay/AUTH-1"

        verified = await provider.verify(
            order_id=order_id,
            reference=intent.reference,
            amount=125_000,
            currency="IRT",
        )
        assert verified.status == ExternalPaymentStatus.PAID
        assert verified.transaction_id == "998877"
        assert len(requests) == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_idpay_request_and_verify() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-KEY"] == "idpay-secret"
        assert request.headers["X-SANDBOX"] == "1"
        payload = __import__("json").loads(request.content)
        if request.url.path.endswith("/verify"):
            assert payload["id"] == "idpay-payment"
            return httpx.Response(
                200,
                json={
                    "status": 100,
                    "amount": 900_000,
                    "track_id": 456789,
                },
            )
        assert payload["amount"] == 900_000
        return httpx.Response(
            200,
            json={
                "id": "idpay-payment",
                "link": "https://idpay.ir/p/idpay-payment",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = IDPayProvider(
        api_key="idpay-secret",
        sandbox=True,
        timeout_seconds=5,
        client=client,
    )
    order_id = uuid4()
    try:
        intent = await provider.create_intent(
            order_id=order_id,
            amount=90_000,
            currency="IRT",
            callback_url="https://example.test/callback",
            description="order",
        )
        verified = await provider.verify(
            order_id=order_id,
            reference=intent.reference,
            amount=90_000,
            currency="IRT",
        )
        assert verified.status == ExternalPaymentStatus.PAID
        assert verified.transaction_id == "456789"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_zibal_request_and_verify() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        if request.url.path.endswith("/request"):
            assert payload["merchant"] == "merchant-zibal"
            assert payload["amount"] == 500_000
            return httpx.Response(
                200,
                json={"result": 100, "trackId": 123456},
            )
        assert payload["trackId"] == 123456
        return httpx.Response(
            200,
            json={
                "result": 100,
                "amount": 500_000,
                "refNumber": "zibal-ref",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = ZibalProvider(
        merchant="merchant-zibal",
        sandbox=False,
        timeout_seconds=5,
        client=client,
    )
    order_id = uuid4()
    try:
        intent = await provider.create_intent(
            order_id=order_id,
            amount=50_000,
            currency="IRT",
            callback_url="https://example.test/callback",
            description="order",
        )
        assert intent.payment_url == "https://gateway.zibal.ir/start/123456"
        verified = await provider.verify(
            order_id=order_id,
            reference=intent.reference,
            amount=50_000,
            currency="IRT",
        )
        assert verified.status == ExternalPaymentStatus.PAID
        assert verified.transaction_id == "zibal-ref"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_nextpay_request_and_verify() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if request.url.path.endswith("/token"):
            assert "amount=75000" in body
            assert "currency=IRT" in body
            return httpx.Response(
                200,
                json={"code": -1, "trans_id": "nextpay-trans"},
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "amount": 75_000,
                "Shaparak_Ref_Id": "nextpay-ref",
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = NextPayProvider(
        api_key="nextpay-key",
        timeout_seconds=5,
        client=client,
    )
    order_id = uuid4()
    try:
        intent = await provider.create_intent(
            order_id=order_id,
            amount=75_000,
            currency="IRT",
            callback_url="https://example.test/callback",
            description="order",
        )
        assert intent.payment_url.endswith("/payment/nextpay-trans")
        verified = await provider.verify(
            order_id=order_id,
            reference=intent.reference,
            amount=75_000,
            currency="IRT",
        )
        assert verified.status == ExternalPaymentStatus.PAID
        assert verified.transaction_id == "nextpay-ref"
    finally:
        await client.aclose()
