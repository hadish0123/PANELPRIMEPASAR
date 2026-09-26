"""External payment intent references.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("provider_reference", sa.String(191), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("payment_url", sa.String(1024), nullable=True),
    )
    op.create_index(
        "ix_payments_provider_reference",
        "payments",
        ["provider_reference"],
    )


def downgrade() -> None:
    op.drop_index("ix_payments_provider_reference", table_name="payments")
    op.drop_column("payments", "payment_url")
    op.drop_column("payments", "provider_reference")
