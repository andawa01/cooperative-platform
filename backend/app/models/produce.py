"""
ProduceLine and Rate.

A ProduceLine is what the cooperative trades: coffee, tea, dairy, etc.
A Rate is the price per unit for a produce line, effective-dated.

Design decisions worth remembering:

1. Rates are APPEND-ONLY. We never edit a rate. When the price changes, the
   current rate gets an effective_to, and a new row is inserted. This gives us
   a full price history that satisfies "which produce line is growing?" and
   "how much did we pay per kg last season?" — without any audit table needed.

2. Rates for the same produce line may NEVER overlap. Enforced by a
   PostgreSQL EXCLUDE constraint using a daterange and the && (overlap)
   operator.

3. Money is NEVER float. We use Numeric(12, 4) → Python Decimal.
   4 decimal places because unit prices can be fractional (0.0085 KES/g).

4. Produce lines are soft-deleted (is_active=False). Historical deliveries
   reference them forever.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text as sql_text

from app.db.base import BaseModel


class ProduceLine(BaseModel):
    __tablename__ = "produce_lines"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        CheckConstraint("length(code) >= 2 AND code ~ '^[a-z0-9_]+$'", name="ck_produce_line_code_format"),
        CheckConstraint("length(unit) >= 1", name="ck_produce_line_unit_not_empty"),
        Index("ix_produce_line_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ProduceLine {self.code} ({self.unit})>"


class Rate(BaseModel):
    __tablename__ = "rates"

    produce_line_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("produce_lines.id", ondelete="RESTRICT"), nullable=False
    )
    rate_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        # The exclusion constraint: no overlapping date ranges for the same produce line.
        ExcludeConstraint(
            ("produce_line_id", "="),
            (sql_text("daterange(effective_from, effective_to, '[)')"), "&&"),
            name="ex_rate_no_overlap",
            using="gist",
        ),
        CheckConstraint("rate_per_unit > 0", name="ck_rate_positive"),
        CheckConstraint("effective_to IS NULL OR effective_to > effective_from", name="ck_rate_date_order"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_rate_currency_iso4217"),
        Index("ix_rate_produce_line_effective", "produce_line_id", "effective_from"),
    )

    def __repr__(self) -> str:
        end = self.effective_to.isoformat() if self.effective_to else "current"
        return f"<Rate {self.rate_per_unit} {self.currency}/{self.produce_line_id} from {self.effective_from} to {end}>"