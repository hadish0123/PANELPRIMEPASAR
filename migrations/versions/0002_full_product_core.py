"""Full product core models.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[object]]:
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
    op.create_table(
        "staff_admins",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("login_username", sa.String(64), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
        sa.UniqueConstraint("login_username"),
    )
    op.create_index(
        "ix_staff_admins_telegram_user_id",
        "staff_admins",
        ["telegram_user_id"],
    )
    op.create_index(
        "ix_staff_admins_login_username",
        "staff_admins",
        ["login_username"],
    )
    op.create_index("ix_staff_admins_is_active", "staff_admins", ["is_active"])

    op.create_table(
        "subscriptions",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("pasar_guard_account_id", sa.Uuid(), nullable=False),
        sa.Column("source_order_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("quota_bytes", sa.BigInteger(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(
            ["pasar_guard_account_id"],
            ["pasarguard_accounts.id"],
        ),
        sa.ForeignKeyConstraint(["source_order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pasar_guard_account_id"),
        sa.UniqueConstraint("source_order_id"),
    )
    op.create_index("ix_subscriptions_customer_id", "subscriptions", ["customer_id"])
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index(
        "ix_subscriptions_pasarguard_account_id",
        "subscriptions",
        ["pasar_guard_account_id"],
    )
    op.create_index(
        "ix_subscriptions_source_order_id",
        "subscriptions",
        ["source_order_id"],
    )
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])

    op.add_column(
        "orders",
        sa.Column(
            "kind",
            sa.String(32),
            nullable=False,
            server_default="new",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("target_subscription_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_orders_target_subscription_id",
        "orders",
        "subscriptions",
        ["target_subscription_id"],
        ["id"],
    )
    op.create_index("ix_orders_kind", "orders", ["kind"])
    op.create_index(
        "ix_orders_target_subscription_id",
        "orders",
        ["target_subscription_id"],
    )
    op.alter_column("orders", "kind", server_default=None)

    op.create_table(
        "support_tickets",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_tickets_customer_id",
        "support_tickets",
        ["customer_id"],
    )
    op.create_index("ix_support_tickets_status", "support_tickets", ["status"])

    op.create_table(
        "support_messages",
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("sender_type", sa.String(32), nullable=False),
        sa.Column("sender_id", sa.String(128), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["ticket_id"], ["support_tickets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_support_messages_ticket_id",
        "support_messages",
        ["ticket_id"],
    )

    op.create_table(
        "wallets",
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("balance", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_id"),
    )
    op.create_index("ix_wallets_customer_id", "wallets", ["customer_id"])

    op.create_table(
        "wallet_transactions",
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("reference", sa.String(191), nullable=True),
        sa.Column("idempotency_key", sa.String(191), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_wallet_transactions_wallet_id",
        "wallet_transactions",
        ["wallet_id"],
    )
    op.create_index("ix_wallet_transactions_kind", "wallet_transactions", ["kind"])
    op.create_index(
        "ix_wallet_transactions_reference",
        "wallet_transactions",
        ["reference"],
    )
    op.create_index(
        "ix_wallet_transactions_idempotency_key",
        "wallet_transactions",
        ["idempotency_key"],
    )

    op.create_table(
        "discount_codes",
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("value_amount", sa.BigInteger(), nullable=True),
        sa.Column("value_percent", sa.Integer(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_discount_codes_code", "discount_codes", ["code"])
    op.create_index(
        "ix_discount_codes_is_active",
        "discount_codes",
        ["is_active"],
    )

    op.create_table(
        "pasarguard_instances",
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("api_key_env_var", sa.String(128), nullable=True),
        sa.Column("bearer_token_env_var", sa.String(128), nullable=True),
        sa.Column("reseller_role_name", sa.String(128), nullable=True),
        sa.Column("reseller_role_id", sa.Integer(), nullable=True),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_health_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_ok", sa.Boolean(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_pasarguard_instances_is_enabled",
        "pasarguard_instances",
        ["is_enabled"],
    )


def downgrade() -> None:
    op.drop_table("pasarguard_instances")
    op.drop_table("discount_codes")
    op.drop_table("wallet_transactions")
    op.drop_table("wallets")
    op.drop_table("support_messages")
    op.drop_table("support_tickets")

    op.drop_index("ix_orders_target_subscription_id", table_name="orders")
    op.drop_index("ix_orders_kind", table_name="orders")
    op.drop_constraint(
        "fk_orders_target_subscription_id",
        "orders",
        type_="foreignkey",
    )
    op.drop_column("orders", "target_subscription_id")
    op.drop_column("orders", "kind")

    op.drop_table("subscriptions")
    op.drop_table("staff_admins")
