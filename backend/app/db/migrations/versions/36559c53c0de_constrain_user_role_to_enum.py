"""constrain user role to enum

Revision ID: 36559c53c0de
Revises: 5f7161fdad79
Create Date: 2026-10-10 12:45:25.878739

NOTE — this migration was hand-edited after autogenerate:
Alembic correctly detected the VARCHAR(50) -> VARCHAR(20) narrowing but did
NOT detect the new CHECK constraint ck_user_role_valid. Alembic autogenerate
is known to miss new CHECK constraints on existing tables. We added the
create/drop calls manually, in a deliberate order:

  1) Add the CHECK constraint first.
  2) Then narrow the column type.

If we narrowed first and any legacy data had a non-conforming role value,
the ALTER would succeed but the CHECK would then fail. Doing the CHECK first
surfaces any such data problem before we touch the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36559c53c0de'
down_revision: Union[str, Sequence[str], None] = '5f7161fdad79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Enforce the closed set of roles.
    op.create_check_constraint(
        "ck_user_role_valid",
        "users",
        "role IN ('admin', 'clerk')",
    )
    # 2. Then narrow the column — safe once roles are constrained.
    op.alter_column(
        'users', 'role',
        existing_type=sa.VARCHAR(length=50),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse order: widen first, then drop the constraint.
    op.alter_column(
        'users', 'role',
        existing_type=sa.String(length=20),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )
    op.drop_constraint("ck_user_role_valid", "users", type_="check")