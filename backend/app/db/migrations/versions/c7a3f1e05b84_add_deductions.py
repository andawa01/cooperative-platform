"""Add the deductions table.

Revision ID: c7a3f1e05b84
Revises: a1c4e7d92f30
Create Date: 2026-11-01

Deductions are the third ledger direction: money withheld from a member's
produce proceeds (transport, cess, input credit, loan recovery, membership
fee, withholding tax). Shape mirrors `payments` so the two can be reasoned
about together — same-table reversals with a negative `amount`, no stored
totals.

Also widens the audit action CHECK to admit `deduction.create` and
`deduction.reverse`. As with `user.update`, the closed set means a new
action needs a migration; the cost buys us a loud failure on a typo.

Downgrade drops the table and narrows the constraint back, which will fail
if deduction audit rows exist. That is correct: silently deleting audit
history to make a rollback succeed would be worse than a failed rollback.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a3f1e05b84"
down_revision: str | Sequence[str] | None = "a1c4e7d92f30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASONS = (
    "transport",
    "cess",
    "input_credit",
    "loan_recovery",
    "membership_fee",
    "withholding_tax",
    "fine",
    "other",
)

ACTIONS_BEFORE = (
    "delivery.create",
    "delivery.value",
    "delivery.reverse",
    "payment.create",
    "payment.reverse",
    "rate.create",
    "farmer.create",
    "farmer.update",
    "farmer.verify",
    "farmer.archive",
    "user.create",
    "user.password_change",
    "user.update",
)

ACTIONS_AFTER = (*ACTIONS_BEFORE, "deduction.create", "deduction.reverse")


def _audit_constraint(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.create_table(
        "deductions",
        sa.Column(
            "farmer_id",
            sa.UUID(),
            sa.ForeignKey("farmers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recorded_by_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "reversal_of_id",
            sa.UUID(),
            sa.ForeignKey("deductions.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
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
        sa.CheckConstraint(
            "(amount > 0 AND reversal_of_id IS NULL) OR "
            "(amount < 0 AND reversal_of_id IS NOT NULL)",
            name="ck_deduction_normal_or_reversal",
        ),
        sa.CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_deduction_no_self_reversal",
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_deduction_currency_iso4217"
        ),
        sa.CheckConstraint(
            "reason_code IN (" + ", ".join(f"'{value}'" for value in REASONS) + ")",
            name="ck_deduction_reason_valid",
        ),
        sa.CheckConstraint(
            "applied_at <= recorded_at + interval '1 hour'",
            name="ck_deduction_applied_at_not_future",
        ),
        sa.UniqueConstraint("reversal_of_id", name="uq_deduction_reversal_of"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deduction_farmer_applied_at", "deductions", ["farmer_id", "applied_at"]
    )
    op.create_index("ix_deduction_applied_at", "deductions", ["applied_at", "id"])
    op.create_index("ix_deduction_reason", "deductions", ["reason_code"])

    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _audit_constraint(ACTIONS_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _audit_constraint(ACTIONS_BEFORE)
    )

    op.drop_index("ix_deduction_reason", table_name="deductions")
    op.drop_index("ix_deduction_applied_at", table_name="deductions")
    op.drop_index("ix_deduction_farmer_applied_at", table_name="deductions")
    op.drop_table("deductions")
