"""
Payout runs — batched settlement of many members at once.

A cooperative pays its members on a date, not one member at a time. This is
the instruction to pay: a batch is created from each member's current payable,
approved by a second party, then dispatched, which records one ordinary
`Payment` per item.

Deliberate choices (see D-032):

- **The amount is snapshotted at creation.** A member's payable moves whenever
  a delivery, payment or deduction is recorded. Once someone has been told
  "you are receiving KES 3,980 on Thursday", a deduction recorded on Wednesday
  must not silently change that number. The item carries its own `amount`.
- **A batch is not a ledger.** It never contributes to `available_credit` or
  `outstanding_debt`. Each dispatched item produces a real `Payment`, which is
  what the ledger sums. Otherwise the same money would be counted twice.
- **Items are individually reversible in effect, collectively auditable.** A
  failed item stays failed with its error; a paid item links to the payment
  that can be reversed through the existing machinery.
- **No gateway yet.** "Dispatched" means the payments are recorded and the run
  is exported as a bank/M-Pesa file. Status per item is honest about what
  actually happened rather than pretending a rail confirmed it.
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
from app.models.payment import PAYMENT_METHOD_VALUES


class PayoutStatus(str, enum.Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    DISPATCHED = "dispatched"
    CANCELLED = "cancelled"


class PayoutItemStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


PAYOUT_STATUS_VALUES = tuple(s.value for s in PayoutStatus)
PAYOUT_ITEM_STATUS_VALUES = tuple(s.value for s in PayoutItemStatus)


class PayoutBatch(BaseModel):
    __tablename__ = "payout_batches"

    # Human-quotable handle ("RUN-2026-3F2A9C"), printed on the bank file and
    # quoted in a settlement meeting. Set right after flush because it embeds
    # the row's own id — see D-032 for why this is not a sequence number.
    reference: Mapped[str | None] = mapped_column(String(24), nullable=True)

    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PayoutStatus.DRAFT.value
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("reference", name="uq_payout_batch_reference"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payout_batch_currency"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{v}'" for v in PAYOUT_STATUS_VALUES) + ")",
            name="ck_payout_batch_status_valid",
        ),
        CheckConstraint(
            "method IN (" + ", ".join(f"'{v}'" for v in PAYMENT_METHOD_VALUES) + ")",
            name="ck_payout_batch_method_valid",
        ),
        # Approval is a fact with an author, not a boolean.
        CheckConstraint(
            "approved_at IS NULL OR approved_by_id IS NOT NULL",
            name="ck_payout_batch_approval_attributed",
        ),
        Index("ix_payout_batch_created", "created_at", "id"),
        Index("ix_payout_batch_status", "status"),
    )

    @property
    def is_cancelled(self) -> bool:
        return self.status == PayoutStatus.CANCELLED.value

    def __repr__(self) -> str:
        return f"<PayoutBatch {self.reference} {self.status}>"


class PayoutItem(BaseModel):
    __tablename__ = "payout_items"

    batch_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payout_batches.id", ondelete="CASCADE"), nullable=False
    )
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=False
    )

    # The member's payable at the moment the run was created. Not recomputed.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PayoutItemStatus.PENDING.value
    )

    # Set when the item is paid. The payment is the ledger fact; this is a
    # pointer to it, so a correction goes through the normal reversal path.
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # A member appears once per run. Re-running is a new batch.
        UniqueConstraint("batch_id", "farmer_id", name="uq_payout_item_member"),
        CheckConstraint("amount > 0", name="ck_payout_item_amount_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_payout_item_currency"),
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{v}'" for v in PAYOUT_ITEM_STATUS_VALUES)
            + ")",
            name="ck_payout_item_status_valid",
        ),
        # Paid means there is a payment to point at; nothing else may claim one.
        CheckConstraint(
            "(status = 'paid' AND payment_id IS NOT NULL) OR "
            "(status <> 'paid' AND payment_id IS NULL)",
            name="ck_payout_item_paid_has_payment",
        ),
        Index("ix_payout_item_batch", "batch_id", "status"),
        Index("ix_payout_item_farmer", "farmer_id"),
    )

    def __repr__(self) -> str:
        return f"<PayoutItem {self.amount} {self.currency} {self.status}>"
