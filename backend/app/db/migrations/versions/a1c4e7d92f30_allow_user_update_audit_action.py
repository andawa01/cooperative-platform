"""Allow the `user.update` audit action.

Revision ID: a1c4e7d92f30
Revises: 5d0cf426e30a
Create Date: 2026-11-01

The audit table's action CHECK constraint is a closed set, so a new action
needs a migration even though the `action` column is a plain VARCHAR. This is
the deliberate cost of the constraint: a misspelt action fails on insert
instead of quietly writing an unqueryable row.

Downgrade note: it will fail if any `user.update` rows exist, because the old
constraint cannot describe them. That is correct — silently deleting audit
history to make a rollback succeed would be far worse than a failed rollback.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1c4e7d92f30"
down_revision: str | Sequence[str] | None = "5d0cf426e30a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
)

ACTIONS_AFTER = (*ACTIONS_BEFORE, "user.update")


def _constraint(values: tuple[str, ...]) -> str:
    return "action IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _constraint(ACTIONS_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("ck_audit_log_action_valid", "audit_log", type_="check")
    op.create_check_constraint(
        "ck_audit_log_action_valid", "audit_log", _constraint(ACTIONS_BEFORE)
    )
