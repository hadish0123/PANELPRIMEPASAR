"""Use gigabyte plan input and remove time limits.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GB = 1_000_000_000


def _upgrade_legacy_gigabyte_values(table: str) -> None:
    # The old web form labelled its raw input as bytes. Production values below
    # one GB were entered as a GB count, so preserve the intended amount.
    op.execute(
        sa.text(
            f"UPDATE {table} "  # noqa: S608 - table names are fixed migration constants
            "SET quota_bytes = quota_bytes * :gb "
            "WHERE quota_bytes > 0 AND quota_bytes < :gb"
        ).bindparams(gb=_GB)
    )


def upgrade() -> None:
    for table in ("plans", "orders", "pasarguard_accounts", "subscriptions"):
        _upgrade_legacy_gigabyte_values(table)

    op.execute("UPDATE plans SET validity_days = NULL WHERE validity_days IS NOT NULL")
    op.execute("UPDATE orders SET validity_days = NULL WHERE validity_days IS NOT NULL")
    op.execute("UPDATE subscriptions SET expires_at = NULL WHERE expires_at IS NOT NULL")


def downgrade() -> None:
    # Converting intended GB counts and removing time limits is intentionally
    # irreversible because the previous values cannot be reconstructed safely.
    pass
