"""Add collection points and structured intake location (D-039).

Revision ID: d93a6f1c4b27
Revises: b7d41c9e2a63
Create Date: 2026-11-07

`collection_points` is reference data: a named, coded point with county/ward/
zone and an optional scale id. Farmers get a nullable home point; deliveries
get the point they actually happened at, nullable for history recorded before
this existed. Both FKs are RESTRICT — a point with history is retired, never
deleted.

Also widens the audit action CHECK for the two point actions.

Downgrade drops the columns, indexes and table, and narrows the constraint;
it fails if a point action has been recorded, which is correct.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d93a6f1c4b27"
down_revision: str | Sequence[str] | None = "b7d41c9e2a63"
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
    "user.update",
    "deduction.create",
    "deduction.reverse",
    "payout.create",
    "payout.approve",
    "payout.dispatch",
    "payout.cancel",
    "approval.request",
    "approval.approve",
    "approval.reject",
)

ACTIONS_AFTER = (
    *ACTIONS_BEFORE,
    "collection_point.create",
    "collection_point.update",
)


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _audit_constraint(values: tuple[str, ...]) -> str:
    return "action IN (" + _quoted(values) + ")"


def upgrade() -> None:
    op.create_table(
        "collection_points",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("county", sa.String(80), nullable=True),
        sa.Column("ward", sa.String(80), nullable=True),
        sa.Column("zone", sa.String(80), nullable=True),
        sa.Column("scale_id", sa.String(64), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_by_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
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
            "code ~ '^[A-Z0-9_-]{2,24}$'", name="ck_collection_point_code_format"
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name="ck_collection_point_name_not_empty"
        ),
        sa.UniqueConstraint("code", name="uq_collection_point_code"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collection_point_active_name", "collection_points", ["is_active", "name"]
    )

    op.add_column("farmers", sa.Column("collection_point_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_farmer_collection_point",
        "farmers",
        "collection_points",
        ["collection_point_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_farmer_collection_point", "farmers", ["collection_point_id"])

    op.add_column(
        "deliveries", sa.Column("collection_point_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_delivery_collection_point",
        "deliveries",
        "collection_points",
        ["collection_point_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_delivery_collection_point",
        "deliveries",
        ["collection_point_id", "delivered_at"],
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

    op.drop_index("ix_delivery_collection_point", table_name="deliveries")
    op.drop_constraint("fk_delivery_collection_point", "deliveries", type_="foreignkey")
    op.drop_column("deliveries", "collection_point_id")

    op.drop_index("ix_farmer_collection_point", table_name="farmers")
    op.drop_constraint("fk_farmer_collection_point", "farmers", type_="foreignkey")
    op.drop_column("farmers", "collection_point_id")

    op.drop_index("ix_collection_point_active_name", table_name="collection_points")
    op.drop_table("collection_points")
