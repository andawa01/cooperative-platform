"""Add maker-checker approval requests (D-038).

Revision ID: b7d41c9e2a63
Revises: c1f4a7d92e38
Create Date: 2026-11-07

One row per second-admin decision. The amount and summary are snapshotted at
request time; `entity_id` deliberately carries no foreign key, so a decision
outlives the payment it refers to, exactly like the audit trail.

The partial unique index is the real guarantee that one subject has one live
request — two admins clicking "request" at the same moment cannot queue two.

Also widens the audit action CHECK to admit the three approval actions.

Downgrade drops the table and narrows the constraint, which fails if approvals
have been recorded. That is correct: history is not deleted to make a
rollback convenient.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d41c9e2a63"
down_revision: str | Sequence[str] | None = "c1f4a7d92e38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIONS = ("payment.reverse", "deduction.reverse", "payout.dispatch")
STATUSES = ("pending", "approved", "rejected")

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
    "payout.create",
    "payout.approve",
    "payout.dispatch",
    "payout.cancel",
)

ACTIONS_AFTER = (
    *ACTIONS_BEFORE,
    "approval.request",
    "approval.approve",
    "approval.reject",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _audit_constraint(values: tuple[str, ...]) -> str:
    return "action IN (" + _quoted(values) + ")"


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("summary", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "requested_by_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "decided_by_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
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
            f"action IN ({_quoted(ACTIONS)})", name="ck_approval_action_valid"
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(STATUSES)})", name="ck_approval_status_valid"
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0", name="ck_approval_amount_positive"
        ),
        sa.CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_approval_currency_iso4217",
        ),
        sa.CheckConstraint(
            "(decided_by_id IS NULL AND decided_at IS NULL) OR "
            "(decided_by_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_approval_decision_attributed",
        ),
        sa.CheckConstraint(
            "decided_by_id IS NULL OR decided_by_id <> requested_by_id",
            name="ck_approval_two_people",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_approval_pending_subject",
        "approval_requests",
        ["action", "entity_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_approval_status_created",
        "approval_requests",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_approval_entity",
        "approval_requests",
        ["entity_type", "entity_id"],
    )

    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _audit_constraint(ACTIONS_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _audit_constraint(ACTIONS_BEFORE)
    )

    op.drop_index("ix_approval_entity", table_name="approval_requests")
    op.drop_index("ix_approval_status_created", table_name="approval_requests")
    op.drop_index("uq_approval_pending_subject", table_name="approval_requests")
    op.drop_table("approval_requests")
