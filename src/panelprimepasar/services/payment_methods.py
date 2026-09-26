import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from panelprimepasar.config import Settings
from panelprimepasar.models import (
    Order,
    Payment,
    PaymentMethodConfig,
    PaymentMethodKind,
    PaymentStatus,
)
from panelprimepasar.payments.base import (
    ExternalPaymentStatus,
    PaymentIntent,
    PaymentProvider,
    PaymentProviderError,
)
from panelprimepasar.payments.providers import (
    IDPayProvider,
    NextPayProvider,
    ZarinPalProvider,
    ZibalProvider,
)
from panelprimepasar.security.payment_secrets import (
    PaymentSecretError,
    decrypt_payment_secrets,
    encrypt_payment_secrets,
)
from panelprimepasar.services.payments import (
    PaymentStateError,
    create_pending_payment,
    fail_payment,
    verify_payment,
)


class PaymentMethodStateError(RuntimeError):
    """Raised when a configured payment method is invalid or unavailable."""


@dataclass(frozen=True, slots=True)
class PaymentMethodInput:
    slug: str
    kind: PaymentMethodKind
    display_name: str
    is_enabled: bool
    sandbox: bool
    sort_order: int
    public_config: Mapping[str, str]
    credentials: Mapping[str, str] | None = None


def normalize_payment_slug(value: str) -> str:
    slug = value.strip().casefold()
    if len(slug) < 2 or len(slug) > 24:
        raise PaymentMethodStateError(
            "Payment method slug must be between 2 and 24 characters"
        )
    if not all(ch.isalnum() or ch in {"_", "-"} for ch in slug):
        raise PaymentMethodStateError(
            "Payment method slug may only contain letters, numbers, _ and -"
        )
    return slug


def parse_public_config(method: PaymentMethodConfig) -> dict[str, str]:
    if not method.public_config_json:
        return {}
    try:
        decoded: object = json.loads(method.public_config_json)
    except json.JSONDecodeError as exc:
        raise PaymentMethodStateError(
            "Stored payment method public configuration is invalid"
        ) from exc
    if not isinstance(decoded, dict):
        raise PaymentMethodStateError(
            "Stored payment method public configuration is invalid"
        )

    result: dict[str, str] = {}
    for key, value in cast(dict[object, object], decoded).items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaymentMethodStateError(
                "Stored payment method public configuration is invalid"
            )
        result[key] = value
    return result


def _master_key(settings: Settings) -> str:
    if settings.payment_credentials_master_key is None:
        raise PaymentMethodStateError(
            "PAYMENT_CREDENTIALS_MASTER_KEY is required for online gateway credentials"
        )
    value = settings.payment_credentials_master_key.get_secret_value()
    if len(value) < 32:
        raise PaymentMethodStateError(
            "PAYMENT_CREDENTIALS_MASTER_KEY must contain at least 32 characters"
        )
    return value


def payment_callback_base_url(settings: Settings) -> str:
    configured = (
        settings.payment_callback_base_url
        or settings.telegram_webhook_base_url
    )
    if configured is None:
        raise PaymentMethodStateError(
            "Configure PAYMENT_CALLBACK_BASE_URL for online payment gateways"
        )
    return str(configured).rstrip("/")


def _normalized_public_config(
    kind: PaymentMethodKind,
    values: Mapping[str, str],
) -> dict[str, str]:
    result = {
        str(key).strip(): str(value).strip()
        for key, value in values.items()
        if str(key).strip() and str(value).strip()
    }

    if kind == PaymentMethodKind.MANUAL_CARD:
        card = (
            result.get("card_number", "")
            .replace(" ", "")
            .replace("-", "")
        )
        if len(card) != 16 or not card.isdecimal():
            raise PaymentMethodStateError(
                "Manual card payment requires a valid 16-digit card_number"
            )
        holder = result.get("card_holder", "")
        if not holder:
            raise PaymentMethodStateError(
                "Manual card payment requires card_holder"
            )
        result["card_number"] = card
    return result


def _validate_credentials(
    *,
    kind: PaymentMethodKind,
    credentials: Mapping[str, str],
    sandbox: bool,
) -> dict[str, str]:
    normalized = {
        str(key).strip(): str(value).strip()
        for key, value in credentials.items()
        if str(key).strip() and str(value).strip()
    }
    required: str | None = None
    if kind == PaymentMethodKind.ZARINPAL:
        required = "merchant_id"
    elif kind == PaymentMethodKind.IDPAY:
        required = "api_key"
    elif kind == PaymentMethodKind.ZIBAL and not sandbox:
        required = "merchant"
    elif kind == PaymentMethodKind.NEXTPAY:
        required = "api_key"

    if required is not None and not normalized.get(required):
        raise PaymentMethodStateError(
            f"{kind.value} requires credential field {required!r}"
        )
    return normalized


def decrypt_method_credentials(
    method: PaymentMethodConfig,
    *,
    settings: Settings,
) -> dict[str, str]:
    if method.kind == PaymentMethodKind.MANUAL_CARD.value:
        return {}
    try:
        return decrypt_payment_secrets(
            method.secret_config_encrypted,
            master_key=_master_key(settings),
        )
    except PaymentSecretError as exc:
        raise PaymentMethodStateError(str(exc)) from exc


async def list_enabled_payment_methods(
    session: AsyncSession,
) -> list[PaymentMethodConfig]:
    rows = await session.scalars(
        select(PaymentMethodConfig)
        .where(PaymentMethodConfig.is_enabled.is_(True))
        .order_by(
            PaymentMethodConfig.sort_order.asc(),
            PaymentMethodConfig.created_at.asc(),
        )
    )
    return list(rows.all())


async def get_payment_method_by_slug(
    session: AsyncSession,
    *,
    slug: str,
    enabled_only: bool = False,
) -> PaymentMethodConfig | None:
    query = select(PaymentMethodConfig).where(
        PaymentMethodConfig.slug == normalize_payment_slug(slug)
    )
    if enabled_only:
        query = query.where(PaymentMethodConfig.is_enabled.is_(True))
    return await session.scalar(query)


async def configure_payment_method(
    session: AsyncSession,
    *,
    settings: Settings,
    values: PaymentMethodInput,
    method_id: UUID | None = None,
) -> PaymentMethodConfig:
    slug = normalize_payment_slug(values.slug)
    display_name = values.display_name.strip()
    if not display_name or len(display_name) > 128:
        raise PaymentMethodStateError(
            "Payment method display name must be between 1 and 128 characters"
        )
    public_config = _normalized_public_config(
        values.kind,
        values.public_config,
    )

    method = (
        await session.get(PaymentMethodConfig, method_id)
        if method_id is not None
        else None
    )
    duplicate = await session.scalar(
        select(PaymentMethodConfig).where(
            PaymentMethodConfig.slug == slug,
            PaymentMethodConfig.id != method_id if method_id is not None else True,
        )
    )
    if duplicate is not None:
        raise PaymentMethodStateError("Payment method slug already exists")

    encrypted_credentials: str | None
    if values.kind == PaymentMethodKind.MANUAL_CARD:
        encrypted_credentials = None
    elif values.credentials is None and method is not None:
        encrypted_credentials = method.secret_config_encrypted
        if not encrypted_credentials:
            raise PaymentMethodStateError(
                "Online gateway credentials are required"
            )
    else:
        credentials = _validate_credentials(
            kind=values.kind,
            credentials=values.credentials or {},
            sandbox=values.sandbox,
        )
        try:
            encrypted_credentials = encrypt_payment_secrets(
                credentials,
                master_key=_master_key(settings),
            )
        except PaymentSecretError as exc:
            raise PaymentMethodStateError(str(exc)) from exc

    if method is None:
        method = PaymentMethodConfig(
            slug=slug,
            kind=values.kind.value,
            display_name=display_name,
            is_enabled=values.is_enabled,
            sandbox=values.sandbox,
            sort_order=values.sort_order,
            public_config_json=json.dumps(
                public_config,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            secret_config_encrypted=encrypted_credentials,
        )
        session.add(method)
    else:
        method.slug = slug
        method.kind = values.kind.value
        method.display_name = display_name
        method.is_enabled = values.is_enabled
        method.sandbox = values.sandbox
        method.sort_order = values.sort_order
        method.public_config_json = json.dumps(
            public_config,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        method.secret_config_encrypted = encrypted_credentials

    await session.flush()
    return method


def build_payment_provider(
    method: PaymentMethodConfig,
    *,
    settings: Settings,
) -> PaymentProvider:
    try:
        kind = PaymentMethodKind(method.kind)
    except ValueError as exc:
        raise PaymentMethodStateError(
            f"Unsupported payment method kind {method.kind!r}"
        ) from exc
    credentials = decrypt_method_credentials(method, settings=settings)

    if kind == PaymentMethodKind.ZARINPAL:
        merchant_id = credentials.get("merchant_id")
        if not merchant_id:
            raise PaymentMethodStateError("ZarinPal merchant_id is missing")
        return ZarinPalProvider(
            merchant_id=merchant_id,
            sandbox=method.sandbox,
            timeout_seconds=settings.payment_http_timeout_seconds,
        )
    if kind == PaymentMethodKind.IDPAY:
        api_key = credentials.get("api_key")
        if not api_key:
            raise PaymentMethodStateError("IDPay api_key is missing")
        return IDPayProvider(
            api_key=api_key,
            sandbox=method.sandbox,
            timeout_seconds=settings.payment_http_timeout_seconds,
        )
    if kind == PaymentMethodKind.ZIBAL:
        merchant = credentials.get("merchant", "")
        if not method.sandbox and not merchant:
            raise PaymentMethodStateError("Zibal merchant is missing")
        return ZibalProvider(
            merchant=merchant,
            sandbox=method.sandbox,
            timeout_seconds=settings.payment_http_timeout_seconds,
        )
    if kind == PaymentMethodKind.NEXTPAY:
        if method.sandbox:
            raise PaymentMethodStateError(
                "NextPay sandbox mode is not supported by this integration"
            )
        api_key = credentials.get("api_key")
        if not api_key:
            raise PaymentMethodStateError("NextPay api_key is missing")
        return NextPayProvider(
            api_key=api_key,
            timeout_seconds=settings.payment_http_timeout_seconds,
        )

    raise PaymentMethodStateError(
        "Manual card payment does not use an online provider client"
    )


async def start_external_payment(
    session: AsyncSession,
    *,
    settings: Settings,
    order: Order,
    method: PaymentMethodConfig,
) -> tuple[Payment, PaymentIntent]:
    if not method.is_enabled:
        raise PaymentMethodStateError("Payment method is disabled")
    if method.kind == PaymentMethodKind.MANUAL_CARD.value:
        raise PaymentMethodStateError(
            "Manual card payment does not create an external payment intent"
        )

    payment = await create_pending_payment(
        session,
        order_id=order.id,
        provider=method.kind,
        payment_method_id=method.id,
    )
    if payment.provider_reference and payment.payment_url:
        return payment, PaymentIntent(
            provider=method.kind,
            reference=payment.provider_reference,
            amount=payment.amount,
            currency=payment.currency,
            status=ExternalPaymentStatus.PENDING,
            payment_url=payment.payment_url,
        )

    provider = build_payment_provider(method, settings=settings)
    try:
        callback_url = (
            f"{payment_callback_base_url(settings)}"
            f"/payments/callback/{payment.id}"
        )
        intent = await provider.create_intent(
            order_id=order.id,
            amount=payment.amount,
            currency=payment.currency,
            callback_url=callback_url,
            description=f"PANELPRIMEPASAR order {order.id}",
        )
    finally:
        await provider.close()

    payment.provider_reference = intent.reference
    payment.payment_url = intent.payment_url
    await session.flush()
    return payment, intent


async def verify_external_payment(
    session: AsyncSession,
    *,
    settings: Settings,
    payment: Payment,
    method: PaymentMethodConfig,
) -> Payment:
    if payment.status == PaymentStatus.VERIFIED:
        return payment
    if payment.status != PaymentStatus.PENDING:
        raise PaymentStateError(
            f"Payment status {payment.status.value!r} cannot be verified"
        )
    if not payment.provider_reference:
        raise PaymentMethodStateError(
            "External payment is missing provider reference"
        )

    provider = build_payment_provider(method, settings=settings)
    try:
        verification = await provider.verify(
            order_id=payment.order_id,
            reference=payment.provider_reference,
            amount=payment.amount,
            currency=payment.currency,
        )
    finally:
        await provider.close()

    if verification.status != ExternalPaymentStatus.PAID:
        return await fail_payment(session, payment_id=payment.id)

    transaction_id = verification.transaction_id or verification.reference
    return await verify_payment(
        session,
        payment_id=payment.id,
        provider_transaction_id=f"{method.kind}:{transaction_id}",
        verified_amount=verification.amount,
        verified_currency=verification.currency,
    )


def payment_method_public_view(
    method: PaymentMethodConfig,
) -> dict[str, object]:
    return {
        "id": str(method.id),
        "slug": method.slug,
        "kind": method.kind,
        "display_name": method.display_name,
        "enabled": method.is_enabled,
        "sandbox": method.sandbox,
        "sort_order": method.sort_order,
        "public_config": parse_public_config(method),
        "credentials_configured": bool(method.secret_config_encrypted),
        "last_check_at": (
            method.last_check_at.isoformat()
            if method.last_check_at is not None
            else None
        ),
        "last_check_ok": method.last_check_ok,
        "last_error_message": method.last_error_message,
    }
