"""Allow the `payment_advice` notification template.

Revision ID: f2a7c9e14b60
Revises: e5c8a13d7f92
Create Date: 2026-11-01

The template column is a VARCHAR with a closed-set CHECK, so a new template
needs a migration — the same deliberate cost as the audit action set. A typo
in a template name should fail on insert, not create a message nobody can query.

`payment_advice` carries the arithmetic behind a payment (what was withheld,
and from which reasons) rather than the bare "payment received" of
`payment_recorded`. Both remain valid: a delivery-confirmation style payment
still uses the plain one.

Downgrade narrows the set back and will fail if advice rows exist. That is
correct — the messages were really sent, so the history must not be rewritten
to make a rollback convenient.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f2a7c9e14b60"
down_revision: str | Sequence[str] | None = "e5c8a13d7f92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATES_BEFORE = ("delivery_recorded", "payment_recorded")
TEMPLATES_AFTER = (*TEMPLATES_BEFORE, "payment_advice")


def _constraint(values: tuple[str, ...]) -> str:
    return "template IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_notification_template_valid", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notification_template_valid", "notifications", _constraint(TEMPLATES_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint("ck_notification_template_valid", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notification_template_valid", "notifications", _constraint(TEMPLATES_BEFORE)
    )
