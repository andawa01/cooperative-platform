"""add user token version

Revision ID: 3f4dcebc9d6d
Revises: e52b47e5ff15
Create Date: 2026-10-20 16:42:00.000000

Adds `users.token_version`, the "sign out everywhere" primitive: access
tokens carry a `ver` claim, and a token whose version no longer matches the
row is rejected. Bumping it on password change invalidates every session for
that user without a session table.

Existing rows default to 0, and tokens minted before this migration have no
`ver` claim — read as 0 — so nobody is logged out by the deploy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f4dcebc9d6d"
down_revision: str | Sequence[str] | None = "e52b47e5ff15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "token_version")
