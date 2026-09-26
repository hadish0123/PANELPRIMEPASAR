"""Commerce metadata and multi-Pasarguard account routing.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
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
    op.add_column(
        "orders",
        sa.Column("discount_code_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "discount_amount",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_foreign_key(
        "fk_orders_discount_code_id",
        "orders",
        "discount_codes",
        ["discount_code_id"],
        ["id"],
    )
    op.create_index(
        "ix_orders_discount_code_id",
        "orders",
        ["discount_code_id"],
    )
    op.alter_column("orders", "discount_amount", server_default=None)

    op.create_table(
        "discount_redemptions",
        sa.Column("discount_code_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["discount_code_id"], ["discount_codes.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index(
        "ix_discount_redemptions_discount_code_id",
        "discount_redemptions",
        ["discount_code_id"],
    )
    op.create_index(
        "ix_discount_redemptions_order_id",
        "discount_redemptions",
        ["order_id"],
    )
    op.create_index(
        "ix_discount_redemptions_customer_id",
        "discount_redemptions",
        ["customer_id"],
    )
    op.create_index(
        "ix_discount_redemptions_status",
        "discount_redemptions",
        ["status"],
    )

    op.add_column(
        "pasarguard_accounts",
        sa.Column("pasarguard_instance_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pasarguard_accounts_instance_id",
        "pasarguard_accounts",
        "pasarguard_instances",
        ["pasarguard_instance_id"],
        ["id"],
    )
    op.create_index(
        "ix_pasarguard_accounts_pasarguard_instance_id",
        "pasarguard_accounts",
        ["pasarguard_instance_id"],
    )

    op.drop_constraint(
        "pasarguard_accounts_pasarguard_admin_id_key",
        "pasarguard_accounts",
        type_="unique",
    )
    op.create_index(
        "uq_pasarguard_accounts_instance_admin_id",
        "pasarguard_accounts",
        ["pasarguard_instance_id", "pasarguard_admin_id"],
        unique=True,
        postgresql_where=sa.text("pasarguard_admin_id IS NOT NULL"),
    )
    op.create_index(
        "uq_pasarguard_accounts_legacy_admin_id",
        "pasarguard_accounts",
        ["pasarguard_admin_id"],
        unique=True,
        postgresql_where=sa.text(
            "pasarguard_instance_id IS NULL AND pasarguard_admin_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_pasarguard_accounts_legacy_admin_id",
        table_name="pasarguard_accounts",
    )
    op.drop_index(
        "uq_pasarguard_accounts_instance_admin_id",
        table_name="pasarguard_accounts",
    )
    op.create_unique_constraint(
        "pasarguard_accounts_pasarguard_admin_id_key",
        "pasarguard_accounts",
        ["pasarguard_admin_id"],
    )
    op.drop_index(
        "ix_pasarguard_accounts_pasarguard_instance_id",
        table_name="pasarguard_accounts",
    )
    op.drop_constraint(
        "fk_pasarguard_accounts_instance_id",
        "pasarguard_accounts",
        type_="foreignkey",
    )
    op.drop_column("pasarguard_accounts", "pasarguard_instance_id")

    op.drop_table("discount_redemptions")
    op.drop_index("ix_orders_discount_code_id", table_name="orders")
    op.drop_constraint(
        "fk_orders_discount_code_id",
        "orders",
        type_="foreignkey",
    )
    op.drop_column("orders", "discount_amount")
    op.drop_column("orders", "discount_code_id")
