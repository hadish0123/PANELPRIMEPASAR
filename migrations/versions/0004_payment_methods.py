"""Configurable payment methods.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
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
        "payment_method_configs",
        sa.Column("slug", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("sandbox", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("public_config_json", sa.Text(), nullable=True),
        sa.Column("secret_config_encrypted", sa.Text(), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_ok", sa.Boolean(), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(
        "ix_payment_method_configs_slug",
        "payment_method_configs",
        ["slug"],
    )
    op.create_index(
        "ix_payment_method_configs_kind",
        "payment_method_configs",
        ["kind"],
    )
    op.create_index(
        "ix_payment_method_configs_is_enabled",
        "payment_method_configs",
        ["is_enabled"],
    )

    op.add_column(
        "payments",
        sa.Column("payment_method_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_payment_method_id",
        "payments",
        "payment_method_configs",
        ["payment_method_id"],
        ["id"],
    )
    op.create_index(
        "ix_payments_payment_method_id",
        "payments",
        ["payment_method_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payments_payment_method_id", table_name="payments")
    op.drop_constraint(
        "fk_payments_payment_method_id",
        "payments",
        type_="foreignkey",
    )
    op.drop_column("payments", "payment_method_id")
    op.drop_table("payment_method_configs")
