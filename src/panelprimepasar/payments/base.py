from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class ExternalPaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"


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
    ) -> PaymentIntent: ...

    async def verify(
        self,
        *,
        reference: str,
    ) -> PaymentVerification: ...
