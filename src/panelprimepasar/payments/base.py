from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ExternalPaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


class PaymentProviderError(RuntimeError):
    """Raised when an external payment provider cannot complete an operation."""


@dataclass(frozen=True, slots=True)
class PaymentIntent:
    provider: str
    reference: str
    amount: int
    currency: str
    status: ExternalPaymentStatus
    payment_url: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentVerification:
    provider: str
    reference: str
    transaction_id: str | None
    amount: int
    currency: str
    status: ExternalPaymentStatus


class PaymentProvider(Protocol):
    name: str

    async def create_intent(
        self,
        *,
        order_id: UUID,
        amount: int,
        currency: str,
        callback_url: str,
        description: str,
    ) -> PaymentIntent: ...

    async def verify(
        self,
        *,
        order_id: UUID,
        reference: str,
        amount: int,
        currency: str,
    ) -> PaymentVerification: ...

    async def close(self) -> None: ...
