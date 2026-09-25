"""Initial commerce and provisioning domain.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    order_status = sa.Enum(
        "pending",
        "awaiting_payment",
        "paid",
        "provisioning",
        "completed",
        "failed",
        "canceled",
        native_enum=False,
        length=32,
    )
    payment_status = sa.Enum(
        "pending",
        "verified",
        "failed",
        "refunded",
        native_enum=False,
        length=32,
    )
    provisioning_status = sa.Enum(
        "pending",
        "running",
        "succeeded",
        "failed",
        native_enum=False,
        length=32,
    )

    op.create_table(
        "customers",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index("ix_customers_telegram_user_id", "customers", ["telegram_user_id"])

    op.create_table(
        "plans",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False),
        sa.Column("price_amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "orders",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("price_amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_idempotency_key", "orders", ["idempotency_key"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "payments",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_transaction_id", sa.String(191), nullable=True),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_reference", sa.String(255), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_transaction_id"),
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "pasarguard_accounts",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("pasarguard_admin_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.Column("role_name", sa.String(128), nullable=True),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("pasarguard_admin_id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(
        "ix_pasarguard_accounts_customer_id",
        "pasarguard_accounts",
        ["customer_id"],
    )

    op.create_table(
        "provisioning_jobs",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("status", provisioning_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_provisioning_jobs_order_id", "provisioning_jobs", ["order_id"])
    op.create_index("ix_provisioning_jobs_status", "provisioning_jobs", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("provisioning_jobs")
    op.drop_table("pasarguard_accounts")
    op.drop_table("payments")
    op.drop_table("orders")
    op.drop_table("plans")
    op.drop_table("customers")
