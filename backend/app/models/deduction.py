"""
Deduction model — money withheld from a member's produce proceeds.

A deduction is a third ledger direction alongside deliveries (credit) and
payments (debit): it is money the member owes the co-op, or money the co-op
remits on their behalf. Real reason codes: transport from the collection point,
cess/levy to the county, recovery of input credit, loan repayment, membership
fee, withholding tax.

Design mirrors Payment deliberately (D-031):

- Same-table reversals. Normal row: positive amount, `reversal_of_id IS NULL`.
  Reversal row: negative amount pointing at the original. Aggregation is
  `SUM(amount)` and the sign does the work, so no query ever has to remember
  to subtract reversals.
- No stored totals anywhere. A member's deductions are derived on read, for
  the same reason balances are (D-010).
- `reason_code` is a closed set enforced by CHECK. A typo in a money field
  must fail loudly, not create an unreportable row.
- `reference` carries the human handle for the charge — an input issue note
  number, a loan account, a county receipt. Optional, because not every
  deduction has one yet.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class DeductionReason(str, enum.Enum):
    TRANSPORT = "transport"
    CESS = "cess"
    INPUT_CREDIT = "input_credit"
    LOAN_RECOVERY = "loan_recovery"
    MEMBERSHIP_FEE = "membership_fee"
    WITHHOLDING_TAX = "withholding_tax"
    FINE = "fine"
    OTHER = "other"


DEDUCTION_REASON_VALUES = tuple(r.value for r in DeductionReason)


class Deduction(BaseModel):
    __tablename__ = "deductions"

    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=False
    )

    # Positive for a charge, negative for its reversal (see constraints).
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # When the charge belongs to (the delivery date, the loan instalment date).
    # For a reversal this copies the original's `applied_at`, so the correction
    # lands in the period it corrects — the same rule delivery reversals follow
    # (D-019).
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # When the clerk entered it.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deductions.id", ondelete="RESTRICT"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Normal vs reversal shape — both sides must agree, as everywhere else.
        CheckConstraint(
            "(amount > 0 AND reversal_of_id IS NULL) OR "
            "(amount < 0 AND reversal_of_id IS NOT NULL)",
            name="ck_deduction_normal_or_reversal",
        ),
        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_deduction_no_self_reversal",
        ),
        # One reversal per original. Multiple NULLs are fine (Postgres treats
        # them as distinct), so normal deductions are unaffected.
        UniqueConstraint("reversal_of_id", name="uq_deduction_reversal_of"),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_deduction_currency_iso4217"
        ),
        CheckConstraint(
            "reason_code IN ("
            + ", ".join(f"'{v}'" for v in DEDUCTION_REASON_VALUES)
            + ")",
            name="ck_deduction_reason_valid",
        ),
        # Same clock-skew tolerance as deliveries and payments.
        CheckConstraint(
            "applied_at <= recorded_at + interval '1 hour'",
            name="ck_deduction_applied_at_not_future",
        ),
        Index("ix_deduction_farmer_applied_at", "farmer_id", "applied_at"),
        Index("ix_deduction_applied_at", "applied_at", "id"),
        Index("ix_deduction_reason", "reason_code"),
    )

    @property
    def is_reversal(self) -> bool:
        return self.reversal_of_id is not None

    def __repr__(self) -> str:
        kind = "REV" if self.is_reversal else "DED"
        return (
            f"<Deduction {kind} {self.amount} {self.reason_code} "
            f"farmer={self.farmer_id} at={self.applied_at}>"
        )
