"""Add member bank details for bank payout files.

Revision ID: c1f4a7d92e38
Revises: b7e2c41d9f03
Create Date: 2026-11-07

A bank transfer run needs a destination the bank can credit. Members have a
phone (mobile money) but no account number, so the bank rail could only refuse
(D-035/D-036). These two nullable columns are set together or not at all, and
the account number is digits only — a wrong digit pays a stranger, so the
shape is checked at the cheapest point rather than discovered by the bank.

No backfill: the data does not exist anywhere to backfill from, and inventing
account numbers would be worse than an empty column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1f4a7d92e38"
down_revision: str | Sequence[str] | None = "b7e2c41d9f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("farmers", sa.Column("bank_name", sa.String(100), nullable=True))
    op.add_column(
        "farmers",
        sa.Column("bank_account_number", sa.String(34), nullable=True),
    )
    op.create_check_constraint(
        "ck_farmer_bank_details_together",
        "farmers",
        "(bank_name IS NULL) = (bank_account_number IS NULL)",
    )
    op.create_check_constraint(
        "ck_farmer_bank_account_digits",
        "farmers",
        "bank_account_number IS NULL OR bank_account_number ~ '^[0-9]{6,20}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_farmer_bank_account_digits", "farmers", type_="check")
    op.drop_constraint("ck_farmer_bank_details_together", "farmers", type_="check")
    op.drop_column("farmers", "bank_account_number")
    op.drop_column("farmers", "bank_name")
