"""
Delivery model — the spine of ShambaTrack.

Every hard problem in this domain flows through deliveries: ghost farmers,
disputed records, farmer trust, produce-line reporting, clerk accountability,
credit history. Getting this table right is the single most consequential
design decision in the project.

See DECISIONS.md D-008 for the full reasoning. Key points:
- Two timestamps: delivered_at (physical event), recorded_at (system fact)
- Immutable: corrections are reversals, never edits
- Reversals live in the same table with negative quantity
- rate_snapshot freezes the rate at time of record
- amount is NOT stored; it's quantity * rate_snapshot computed at read time
- No partial reversals in MVP
"""

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


class Delivery(BaseModel):
    __tablename__ = "deliveries"

    # --- Who and what ---------------------------------------------------
    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=False
    )
    produce_line_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("produce_lines.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Quantity -------------------------------------------------------
    # Positive for a delivery, negative for a reversal (see constraints).
    # Unit is implied by the produce line, not stored per delivery.
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    # --- Timestamps -----------------------------------------------------
    # When the physical delivery happened. For reversals, this MATCHES the
    # original's delivered_at so the reversal sits in the period it corrects.
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # When the clerk entered the record. May differ from delivered_at by days.
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # --- Clerk accountability ------------------------------------------
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Valuation snapshot --------------------------------------------
    # Frozen at record time. If no rate was available for delivered_at,
    # this is NULL and the delivery is "pending valuation" (derived state).
    rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    currency_snapshot: Mapped[str] = mapped_column(String(3), nullable=False)

    # --- Reversal linkage ----------------------------------------------
    # NULL for normal deliveries. Set (and quantity < 0) for reversals.
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=True
    )

    # --- Context --------------------------------------------------------
    # Free-text for now; will be replaced by a collection_point_id FK later.
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Constraints ----------------------------------------------------
    __table_args__ = (
        # A normal delivery has positive quantity and no reversal link.
        # A reversal has negative quantity and a reversal link.
        # Both sides of this equation must agree — same trick as farmers.
        CheckConstraint(
            "(quantity > 0 AND reversal_of_id IS NULL) OR "
            "(quantity < 0 AND reversal_of_id IS NOT NULL)",
            name="ck_delivery_normal_or_reversal",
        ),
        # A delivery can't be a reversal of itself.
        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id <> id",
            name="ck_delivery_no_self_reversal",
        ),
        # Rate, when present, must be positive.
        CheckConstraint(
            "rate_snapshot IS NULL OR rate_snapshot > 0",
            name="ck_delivery_rate_positive",
        ),
        # Currency is ISO 4217 (3 uppercase letters).
        CheckConstraint(
            "currency_snapshot ~ '^[A-Z]{3}$'",
            name="ck_delivery_currency_iso4217",
        ),
        # Physical event cannot be recorded AFTER the fact by more than a
        # tolerance (handles clock skew). Backdated deliveries are fine —
        # this only prevents future-dated records.
        CheckConstraint(
            "delivered_at <= recorded_at + interval '1 hour'",
            name="ck_delivery_delivered_at_not_future",
        ),
        # No double-reversal: at most one reversal per original.
        # Multiple NULLs allowed (Postgres treats NULLs as distinct in
        # unique constraints), so normal deliveries are unaffected.
        UniqueConstraint("reversal_of_id", name="uq_delivery_reversal_of"),
        # Query indexes for the common access patterns.
        Index("ix_delivery_farmer_delivered_at", "farmer_id", "delivered_at"),
        Index(
            "ix_delivery_produce_line_delivered_at",
            "produce_line_id",
            "delivered_at",
        ),
        # The delivery list orders globally by (delivered_at, id), which the
        # farmer-first composite index above cannot serve. `id` is included so
        # the tie-break needs no sort.
        Index("ix_delivery_delivered_at", "delivered_at", "id"),
        Index("ix_delivery_recorded_by", "recorded_by_id"),
    )

    # --- Derived helpers ------------------------------------------------
    @property
    def amount(self) -> Decimal | None:
        """
        Computed at read time. None if rate_snapshot is missing (unvalued).

        Uses Decimal arithmetic — never float. Callers who need a specific
        rounding policy should round explicitly rather than relying on this.
        """
        if self.rate_snapshot is None:
            return None
        return self.quantity * self.rate_snapshot

    @property
    def is_reversal(self) -> bool:
        return self.reversal_of_id is not None

    @property
    def is_valued(self) -> bool:
        return self.rate_snapshot is not None

    def __repr__(self) -> str:
        kind = "REV" if self.is_reversal else "DEL"
        return (
            f"<Delivery {kind} {self.quantity} {self.produce_line_id} "
            f"farmer={self.farmer_id} at={self.delivered_at}>"
        )
