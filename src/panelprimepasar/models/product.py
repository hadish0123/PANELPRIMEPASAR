from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from panelprimepasar.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from panelprimepasar.security.permissions import AdminRole


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELED = "canceled"


class TicketStatus(StrEnum):
    OPEN = "open"
    PENDING = "pending"
    ANSWERED = "answered"
    CLOSED = "closed"


class WalletTransactionKind(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"
    REFUND = "refund"
    COMMISSION = "commission"
    ADJUSTMENT = "adjustment"


class DiscountKind(StrEnum):
    FIXED = "fixed"
    PERCENT = "percent"


class DiscountRedemptionStatus(StrEnum):
    RESERVED = "reserved"
    REDEEMED = "redeemed"
    RELEASED = "released"


class PaymentMethodKind(StrEnum):
    MANUAL_CARD = "manual_card"
    ZARINPAL = "zarinpal"
    IDPAY = "idpay"
    ZIBAL = "zibal"
    NEXTPAY = "nextpay"


class StaffAdmin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "staff_admins"

    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    login_username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=AdminRole.SUPPORT.value)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"), index=True)
    pasar_guard_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("pasarguard_accounts.id"),
        unique=True,
        index=True,
    )
    source_order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SubscriptionStatus.ACTIVE.value,
        index=True,
    )
    quota_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SupportTicket(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_tickets"

    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=TicketStatus.OPEN.value,
        index=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_messages"

    ticket_id: Mapped[UUID] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    sender_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Wallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallets"

    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id"),
        unique=True,
        index=True,
    )
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="IRT")


class WalletTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wallet_transactions"

    wallet_id: Mapped[UUID] = mapped_column(ForeignKey("wallets.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(191), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(191), unique=True, index=True)


class DiscountCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "discount_codes"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value_amount: Mapped[int | None] = mapped_column(BigInteger)
    value_percent: Mapped[int | None] = mapped_column(Integer)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class DiscountRedemption(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "discount_redemptions"

    discount_code_id: Mapped[UUID] = mapped_column(
        ForeignKey("discount_codes.id"),
        index=True,
    )
    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id"),
        unique=True,
        index=True,
    )
    customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("customers.id"),
        index=True,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DiscountRedemptionStatus.RESERVED.value,
        index=True,
    )


class PaymentMethodConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_method_configs"

    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    public_config_json: Mapped[str | None] = mapped_column(Text)
    secret_config_encrypted: Mapped[str | None] = mapped_column(Text)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_error_message: Mapped[str | None] = mapped_column(Text)


class PasarGuardInstance(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pasarguard_instances"

    name: Mapped[str] = mapped_column(String(128), unique=True)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_env_var: Mapped[str | None] = mapped_column(String(128))
    bearer_token_env_var: Mapped[str | None] = mapped_column(String(128))
    reseller_role_name: Mapped[str | None] = mapped_column(String(128))
    reseller_role_id: Mapped[int | None] = mapped_column(Integer)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    last_health_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_health_ok: Mapped[bool | None] = mapped_column(Boolean)
