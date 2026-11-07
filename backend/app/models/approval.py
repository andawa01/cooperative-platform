"""
Approval requests — the second pair of eyes on large money moves (D-038).

A cooperative's exposure is not the small payment at the counter; it is the
one admin who can reverse a large payment, or release a payroll-sized run,
without anyone else looking. This table is the record of that second look.

Shape:

- **The request names the fact, not the intent.** `action` + `entity_type` +
  `entity_id` point at the payment, deduction or run being asked about, and
  `amount` is captured when the request is made. The approver sees the same
  number the requester did, even if the member's balance has moved since.
- **A decision is attributed.** `decided_by_id` + `decided_at` are set
  together, enforced by a CHECK; a rejection carries the note that explains
  it. An approval without an approver is not a thing this table can store.
- **Two people, enforced by the database.** `requested_by_id <> decided_by_id`
  is a CHECK, not a service convention, so a bug (or a later endpoint) cannot
  let one admin approve their own request.
- **One pending request per subject.** A partial unique index keeps a second
  click from queuing a duplicate for the same payment.
- **Approval does not execute by itself.** The service calls the same
  function the direct endpoint would, with the approving admin as the actor —
  there is no second write path to drift.
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
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


APPROVAL_STATUS_VALUES = tuple(s.value for s in ApprovalStatus)

# The actions that can be gated. Deliberately a small closed set: a new
# money-moving endpoint is a decision to make, not a flag to flip.
APPROVAL_ACTIONS = (
    "payment.reverse",
    "deduction.reverse",
    "payout.dispatch",
)

APPROVAL_ACTION_VALUES = APPROVAL_ACTIONS


class ApprovalRequest(BaseModel):
    __tablename__ = "approval_requests"

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # A plain UUID, like the audit trail: the request is evidence of a
    # decision, and must survive whatever it points at.
    entity_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Snapshot of what the approver is agreeing to. Nullable for actions that
    # release no single amount (none today), so the column can stay honest
    # instead of carrying a zero.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    # Readable one-liner for the queue: "Reverse a KES 25,000.00 payment to
    # Jane Wambui". Built once, so the queue never has to join three tables.
    summary: Mapped[str] = mapped_column(String(255), nullable=False)

    # The requester's words. They become the reason on the reversal the
    # approver executes, so the trail reads the same end to end.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApprovalStatus.PENDING.value
    )

    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action IN (" + ", ".join(f"'{a}'" for a in APPROVAL_ACTIONS) + ")",
            name="ck_approval_action_valid",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{v}'" for v in APPROVAL_STATUS_VALUES) + ")",
            name="ck_approval_status_valid",
        ),
        CheckConstraint(
            "amount IS NULL OR amount > 0", name="ck_approval_amount_positive"
        ),
        CheckConstraint(
            "currency IS NULL OR currency ~ '^[A-Z]{3}$'",
            name="ck_approval_currency_iso4217",
        ),
        # A decision is a fact with an author and a time, or it did not happen.
        CheckConstraint(
            "(decided_by_id IS NULL AND decided_at IS NULL) OR "
            "(decided_by_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_approval_decision_attributed",
        ),
        # The control itself: the person who asked cannot be the person who
        # agreed.
        CheckConstraint(
            "decided_by_id IS NULL OR decided_by_id <> requested_by_id",
            name="ck_approval_two_people",
        ),
        # One live request per subject. Re-asking returns the pending one.
        Index(
            "uq_approval_pending_subject",
            "action",
            "entity_type",
            "entity_id",
            unique=True,
            postgresql_where="status = 'pending'",
        ),
        Index("ix_approval_status_created", "status", "created_at"),
        Index("ix_approval_entity", "entity_type", "entity_id"),
    )

    @property
    def is_pending(self) -> bool:
        return self.status == ApprovalStatus.PENDING.value

    def __repr__(self) -> str:
        return f"<ApprovalRequest {self.action} {self.entity_id} {self.status}>"
