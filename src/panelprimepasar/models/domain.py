from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from panelprimepasar.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrderKind(StrEnum):
    NEW = "new"
    RENEWAL = "renewal"
    TOPUP = "topup"


class OrderStatus(StrEnum):
    PENDING = "pending"
    AWAITING_PAYMENT = "awaiting_payment"
    PAID = "paid"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    REFUNDED = "refunded"


class ProvisioningStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customers"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    quota_bytes: Mapped[int] = mapped_column(BigInteger)
    price_amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8))
    validity_days: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"

    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"))
    kind: Mapped[OrderKind] = mapped_column(
        Enum(OrderKind, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
        default=OrderKind.NEW,
        index=True,
    )
    target_subscription_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("subscriptions.id"),
        index=True,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
    )
    price_amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8))
    quota_bytes: Mapped[int] = mapped_column(BigInteger)
    validity_days: Mapped[int | None] = mapped_column(Integer)
    discount_code_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("discount_codes.id"),
        index=True,
    )
    discount_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_transaction_id: Mapped[str | None] = mapped_column(String(191), unique=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_reference: Mapped[str | None] = mapped_column(String(255))


class PasarGuardAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pasarguard_accounts"

    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    pasarguard_admin_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    role_id: Mapped[int | None] = mapped_column(Integer)
    role_name: Mapped[str | None] = mapped_column(String(128))
    quota_bytes: Mapped[int] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ProvisioningJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "provisioning_jobs"

    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id"), unique=True, index=True)
    status: Mapped[ProvisioningStatus] = mapped_column(
        Enum(ProvisioningStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
        default=ProvisioningStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(128), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(128), index=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text)
