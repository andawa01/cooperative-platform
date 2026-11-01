"""Add payout runs (batches and items).

Revision ID: e5c8a13d7f92
Revises: c7a3f1e05b84
Create Date: 2026-11-01

A payout run is the instruction to pay many members at once. It stores the
amount each member was owed at the moment the run was created, then links to
the real `Payment` each item produced. It never contributes to the ledger
itself — see D-032 and `app/models/payout.py`.

Also widens the audit action CHECK to admit the four run actions, the same
closed-set cost as `user.update` and the deduction actions before it.

Downgrade drops both tables and narrows the constraint, which will fail if a
payout action has already been recorded. That is correct: audit history is not
deleted to make a rollback convenient.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5c8a13d7f92"
down_revision: str | Sequence[str] | None = "c7a3f1e05b84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

METHODS = ("cash", "mobile_money", "bank_transfer")
BATCH_STATUSES = ("draft", "approved", "dispatched", "cancelled")
ITEM_STATUSES = ("pending", "paid", "failed", "cancelled")

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
    "deduction.create",
    "deduction.reverse",
)

ACTIONS_AFTER = (
    *ACTIONS_BEFORE,
    "payout.create",
    "payout.approve",
    "payout.dispatch",
    "payout.cancel",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _audit_constraint(values: tuple[str, ...]) -> str:
    return "action IN (" + _quoted(values) + ")"


def upgrade() -> None:
    op.create_table(
        "payout_batches",
        sa.Column("reference", sa.String(24), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "approved_by_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payout_batch_currency"),
        sa.CheckConstraint(
            f"status IN ({_quoted(BATCH_STATUSES)})",
            name="ck_payout_batch_status_valid",
        ),
        sa.CheckConstraint(
            f"method IN ({_quoted(METHODS)})",
            name="ck_payout_batch_method_valid",
        ),
        sa.CheckConstraint(
            "approved_at IS NULL OR approved_by_id IS NOT NULL",
            name="ck_payout_batch_approval_attributed",
        ),
        sa.UniqueConstraint("reference", name="uq_payout_batch_reference"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payout_batch_created", "payout_batches", ["created_at", "id"])
    op.create_index("ix_payout_batch_status", "payout_batches", ["status"])

    op.create_table(
        "payout_items",
        sa.Column(
            "batch_id",
            sa.UUID(),
            sa.ForeignKey("payout_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "farmer_id",
            sa.UUID(),
            sa.ForeignKey("farmers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "payment_id",
            sa.UUID(),
            sa.ForeignKey("payments.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("amount > 0", name="ck_payout_item_amount_positive"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payout_item_currency"),
        sa.CheckConstraint(
            f"status IN ({_quoted(ITEM_STATUSES)})",
            name="ck_payout_item_status_valid",
        ),
        sa.CheckConstraint(
            "(status = 'paid' AND payment_id IS NOT NULL) OR "
            "(status <> 'paid' AND payment_id IS NULL)",
            name="ck_payout_item_paid_has_payment",
        ),
        sa.UniqueConstraint("batch_id", "farmer_id", name="uq_payout_item_member"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payout_item_batch", "payout_items", ["batch_id", "status"])
    op.create_index("ix_payout_item_farmer", "payout_items", ["farmer_id"])

    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _audit_constraint(ACTIONS_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _audit_constraint(ACTIONS_BEFORE)
    )

    op.drop_index("ix_payout_item_farmer", table_name="payout_items")
    op.drop_index("ix_payout_item_batch", table_name="payout_items")
    op.drop_table("payout_items")

    op.drop_index("ix_payout_batch_status", table_name="payout_batches")
    op.drop_index("ix_payout_batch_created", table_name="payout_batches")
    op.drop_table("payout_batches")
