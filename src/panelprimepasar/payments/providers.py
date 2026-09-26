from __future__ import annotations

from typing import cast
from uuid import UUID

import httpx

from panelprimepasar.payments.base import (
    ExternalPaymentStatus,
    PaymentIntent,
    PaymentProviderError,
    PaymentVerification,
)


def _to_irr(amount: int, currency: str) -> int:
    normalized = currency.upper()
    if normalized == "IRR":
        return amount
    if normalized == "IRT":
        return amount * 10
    raise PaymentProviderError(
        f"Unsupported payment currency {currency!r}; only IRT and IRR are supported"
    )


def _json_object(response: httpx.Response) -> dict[str, object]:
    try:
        payload: object = response.json()
    except ValueError as exc:
        raise PaymentProviderError("Payment provider returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise PaymentProviderError("Payment provider returned an invalid response")
    return cast(dict[str, object], payload)


def _string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return str(value)
    return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


class _HttpPaymentProvider:
    name: str

    def __init__(
        self,
        *,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    async def _post_json(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        try:
            response = await self._client.post(
                url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentProviderError(
                f"{self.name} payment service could not be reached"
            ) from exc
        return _json_object(response)

    async def _post_form(
        self,
        url: str,
        *,
        payload: dict[str, str],
    ) -> dict[str, object]:
        try:
            response = await self._client.post(url, data=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PaymentProviderError(
                f"{self.name} payment service could not be reached"
            ) from exc
        return _json_object(response)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class ZarinPalProvider(_HttpPaymentProvider):
    name = "zarinpal"

    def __init__(
        self,
        *,
        merchant_id: str,
        sandbox: bool,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, client=client)
        self.merchant_id = merchant_id
        self.sandbox = sandbox
        if sandbox:
            self._api_base = "https://sandbox.zarinpal.com"
            self._payment_base = "https://sandbox.zarinpal.com"
        else:
            self._api_base = "https://api.zarinpal.com"
            self._payment_base = "https://www.zarinpal.com"

    async def create_intent(
        self,
        *,
        order_id: UUID,
        amount: int,
        currency: str,
        callback_url: str,
        description: str,
    ) -> PaymentIntent:
        rial_amount = _to_irr(amount, currency)
        payload = await self._post_json(
            f"{self._api_base}/pg/v4/payment/request.json",
            payload={
                "merchant_id": self.merchant_id,
                "amount": rial_amount,
                "callback_url": callback_url,
                "description": description,
                "metadata": {"order_id": str(order_id)},
            },
        )
        data_raw = payload.get("data")
        data = (
            cast(dict[str, object], data_raw)
            if isinstance(data_raw, dict)
            else {}
        )
        code = _integer(data.get("code"))
        authority = _string(data.get("authority"))
        if code != 100 or authority is None:
            errors = payload.get("errors")
            raise PaymentProviderError(
                f"ZarinPal rejected payment request: {errors or code or 'unknown error'}"
            )

        return PaymentIntent(
            provider=self.name,
            reference=authority,
            amount=amount,
            currency=currency.upper(),
            status=ExternalPaymentStatus.PENDING,
            payment_url=f"{self._payment_base}/pg/StartPay/{authority}",
        )

    async def verify(
        self,
        *,
        order_id: UUID,
        reference: str,
        amount: int,
        currency: str,
    ) -> PaymentVerification:
        del order_id
        payload = await self._post_json(
            f"{self._api_base}/pg/v4/payment/verify.json",
            payload={
                "merchant_id": self.merchant_id,
                "amount": _to_irr(amount, currency),
                "authority": reference,
            },
        )
        data_raw = payload.get("data")
        data = (
            cast(dict[str, object], data_raw)
            if isinstance(data_raw, dict)
            else {}
        )
        code = _integer(data.get("code"))
        paid = code in {100, 101}
        transaction_id = _string(data.get("ref_id")) if paid else None
        return PaymentVerification(
            provider=self.name,
            reference=reference,
            transaction_id=transaction_id or (reference if paid else None),
            amount=amount,
            currency=currency.upper(),
            status=(
                ExternalPaymentStatus.PAID
                if paid
                else ExternalPaymentStatus.FAILED
            ),
        )


class IDPayProvider(_HttpPaymentProvider):
    name = "idpay"

    def __init__(
        self,
        *,
        api_key: str,
        sandbox: bool,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, client=client)
        self.api_key = api_key
        self.sandbox = sandbox
        self._headers = {
            "X-API-KEY": api_key,
            "X-SANDBOX": "1" if sandbox else "0",
        }
        self._base = "https://api.idpay.ir/v1.1/payment"

    async def create_intent(
        self,
        *,
        order_id: UUID,
        amount: int,
        currency: str,
        callback_url: str,
        description: str,
    ) -> PaymentIntent:
        payload = await self._post_json(
            self._base,
            headers=self._headers,
            payload={
                "order_id": str(order_id),
                "amount": _to_irr(amount, currency),
                "desc": description,
                "callback": callback_url,
            },
        )
        reference = _string(payload.get("id"))
        link = _string(payload.get("link"))
        if reference is None or link is None:
            raise PaymentProviderError(
                f"IDPay rejected payment request: {payload.get('error_message') or payload.get('error_code') or 'unknown error'}"
            )
        return PaymentIntent(
            provider=self.name,
            reference=reference,
            amount=amount,
            currency=currency.upper(),
            status=ExternalPaymentStatus.PENDING,
            payment_url=link,
        )

    async def verify(
        self,
        *,
        order_id: UUID,
        reference: str,
        amount: int,
        currency: str,
    ) -> PaymentVerification:
        payload = await self._post_json(
            f"{self._base}/verify",
            headers=self._headers,
            payload={
                "id": reference,
                "order_id": str(order_id),
            },
        )
        status = _integer(payload.get("status"))
        remote_amount = _integer(payload.get("amount"))
        expected_amount = _to_irr(amount, currency)
        paid = status in {100, 101}
        if paid and remote_amount is not None and remote_amount != expected_amount:
            raise PaymentProviderError("IDPay verified amount does not match order")

        transaction_id = (
            _string(payload.get("track_id"))
            or _string(payload.get("payment"))
            or reference
        )
        return PaymentVerification(
            provider=self.name,
            reference=reference,
            transaction_id=transaction_id if paid else None,
            amount=amount,
            currency=currency.upper(),
            status=(
                ExternalPaymentStatus.PAID
                if paid
                else ExternalPaymentStatus.FAILED
            ),
        )


class ZibalProvider(_HttpPaymentProvider):
    name = "zibal"

    def __init__(
        self,
        *,
        merchant: str,
        sandbox: bool,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, client=client)
        self.merchant = "zibal" if sandbox else merchant
        self.sandbox = sandbox
        self._base = "https://gateway.zibal.ir/v1"

    async def create_intent(
        self,
        *,
        order_id: UUID,
        amount: int,
        currency: str,
        callback_url: str,
        description: str,
    ) -> PaymentIntent:
        payload = await self._post_json(
            f"{self._base}/request",
            payload={
                "merchant": self.merchant,
                "amount": _to_irr(amount, currency),
                "callbackUrl": callback_url,
                "description": description,
                "orderId": str(order_id),
            },
        )
        result = _integer(payload.get("result"))
        track_id = _string(payload.get("trackId"))
        if result != 100 or track_id is None:
            raise PaymentProviderError(
                f"Zibal rejected payment request: {payload.get('message') or result or 'unknown error'}"
            )
        return PaymentIntent(
            provider=self.name,
            reference=track_id,
            amount=amount,
            currency=currency.upper(),
            status=ExternalPaymentStatus.PENDING,
            payment_url=f"https://gateway.zibal.ir/start/{track_id}",
        )

    async def verify(
        self,
        *,
        order_id: UUID,
        reference: str,
        amount: int,
        currency: str,
    ) -> PaymentVerification:
        del order_id
        payload = await self._post_json(
            f"{self._base}/verify",
            payload={
                "merchant": self.merchant,
                "trackId": int(reference),
            },
        )
        result = _integer(payload.get("result"))
        paid = result in {100, 201}
        remote_amount = _integer(payload.get("amount"))
        if paid and remote_amount is not None and remote_amount != _to_irr(amount, currency):
            raise PaymentProviderError("Zibal verified amount does not match order")
        transaction_id = (
            _string(payload.get("refNumber"))
            or _string(payload.get("cardNumber"))
            or reference
        )
        return PaymentVerification(
            provider=self.name,
            reference=reference,
            transaction_id=transaction_id if paid else None,
            amount=amount,
            currency=currency.upper(),
            status=(
                ExternalPaymentStatus.PAID
                if paid
                else ExternalPaymentStatus.FAILED
            ),
        )


class NextPayProvider(_HttpPaymentProvider):
    name = "nextpay"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds, client=client)
        self.api_key = api_key
        self._base = "https://nextpay.org/nx/gateway"

    async def create_intent(
        self,
        *,
        order_id: UUID,
        amount: int,
        currency: str,
        callback_url: str,
        description: str,
    ) -> PaymentIntent:
        normalized_currency = currency.upper()
        if normalized_currency not in {"IRT", "IRR"}:
            raise PaymentProviderError(
                "NextPay only supports IRT and IRR in this integration"
            )
        payload = await self._post_form(
            f"{self._base}/token",
            payload={
                "api_key": self.api_key,
                "order_id": str(order_id),
                "amount": str(amount),
                "callback_uri": callback_url,
                "currency": normalized_currency,
                "payer_desc": description,
            },
        )
        code = _integer(payload.get("code"))
        trans_id = _string(payload.get("trans_id"))
        if code != -1 or trans_id is None:
            raise PaymentProviderError(
                f"NextPay rejected payment request: {payload.get('message') or code or 'unknown error'}"
            )
        return PaymentIntent(
            provider=self.name,
            reference=trans_id,
            amount=amount,
            currency=normalized_currency,
            status=ExternalPaymentStatus.PENDING,
            payment_url=f"{self._base}/payment/{trans_id}",
        )

    async def verify(
        self,
        *,
        order_id: UUID,
        reference: str,
        amount: int,
        currency: str,
    ) -> PaymentVerification:
        del order_id
        normalized_currency = currency.upper()
        payload = await self._post_form(
            f"{self._base}/verify",
            payload={
                "api_key": self.api_key,
                "trans_id": reference,
                "amount": str(amount),
                "currency": normalized_currency,
            },
        )
        code = _integer(payload.get("code"))
        remote_amount = _integer(payload.get("amount"))
        paid = code == 0
        if paid and remote_amount is not None and remote_amount != amount:
            raise PaymentProviderError("NextPay verified amount does not match order")
        transaction_id = (
            _string(payload.get("Shaparak_Ref_Id"))
            or _string(payload.get("shaparak_ref_id"))
            or reference
        )
        return PaymentVerification(
            provider=self.name,
            reference=reference,
            transaction_id=transaction_id if paid else None,
            amount=amount,
            currency=normalized_currency,
            status=(
                ExternalPaymentStatus.PAID
                if paid
                else ExternalPaymentStatus.FAILED
            ),
        )
