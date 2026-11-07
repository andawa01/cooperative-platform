"""Add delivery receipt numbers.

Revision ID: b7e2c41d9f03
Revises: f2a7c9e14b60
Create Date: 2026-11-07

Every delivery now carries a short sequential handle (`D-2026-000123`) that a
member can quote, printed on the delivery SMS and exported in the CSV. The
counter lives in `document_sequences`, one row per document family and year;
see D-034.

Existing deliveries are numbered in the order they were recorded, restarting
at 1 for each calendar year of `delivered_at`, and each year's counter is
seeded from the backfill. Reversals are corrections rather than intake slips,
so they stay NULL.

Downgrade drops the column, which discards the numbering. That is acceptable:
the numbers are derivable again from the same ordering.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c41d9f03"
down_revision: str | Sequence[str] | None = "f2a7c9e14b60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
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
        sa.CheckConstraint("last_value >= 0", name="ck_document_sequence_non_negative"),
        sa.UniqueConstraint("name", "year", name="uq_document_sequence_scope"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "deliveries", sa.Column("receipt_number", sa.String(24), nullable=True)
    )
    op.create_unique_constraint(
        "uq_delivery_receipt_number", "deliveries", ["receipt_number"]
    )

    # Number what already exists, in record order, per delivery year.
    op.execute(
        """
        WITH numbered AS (
            SELECT id,
                   EXTRACT(year FROM delivered_at)::int AS yr,
                   row_number() OVER (
                       PARTITION BY EXTRACT(year FROM delivered_at)
                       ORDER BY recorded_at, id
                   ) AS rn
              FROM deliveries
             WHERE reversal_of_id IS NULL
        )
        UPDATE deliveries d
           SET receipt_number = 'D-' || n.yr || '-' || lpad(n.rn::text, 6, '0')
          FROM numbered n
         WHERE d.id = n.id
        """
    )

    # Seed each year's counter from the highest number the backfill issued.
    op.execute(
        """
        INSERT INTO document_sequences
            (id, name, year, last_value, created_at, updated_at)
        SELECT gen_random_uuid(), 'delivery_receipt', yr, cnt, now(), now()
          FROM (
              SELECT EXTRACT(year FROM delivered_at)::int AS yr, count(*) AS cnt
                FROM deliveries
               WHERE receipt_number IS NOT NULL
               GROUP BY 1
          ) AS per_year
        """
    )


def downgrade() -> None:
    op.drop_constraint("uq_delivery_receipt_number", "deliveries", type_="unique")
    op.drop_column("deliveries", "receipt_number")
    op.drop_table("document_sequences")
