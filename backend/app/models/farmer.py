"""
Farmer model.

A Farmer is a PERSON who delivers produce to the cooperative and receives
payment. A Farmer is deliberately NOT a User — a farmer can exist in the
system without ever logging in. Clerks register farmers and act on their
behalf. If we later want farmers to log in, we add a link table, not fields
here.

Design invariants (enforced at DB level where possible):
1. Phone is unique (E.164) — SMS goes to it, duplicates = money to wrong person
2. National ID is unique WHEN PRESENT — anti-"ghost farmer"
3. A farmer cannot be merged into themselves
4. status = 'merged' <=> merged_into_id IS NOT NULL (both directions)
5. verified_at and verified_by_id are set together or not at all
6. Farmers are never hard-deleted — only status changes

Application-level invariants (cannot be DB-enforced):
7. Merged farmers cannot receive new deliveries or payments
8. Merge chains (A→B→C) must be resolved when reading history
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class FarmerStatus(str, enum.Enum):
    """
    Mirrors the CHECK constraint in the DB. Kept as str-enum so it serializes
    cleanly to JSON and can be compared to raw strings.
    """

    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"
    MERGED = "merged"


# Single source of truth for the CHECK constraint. If we add a status, we
# update this tuple — and only this tuple — and write a migration.
FARMER_STATUS_VALUES = tuple(s.value for s in FarmerStatus)


class Farmer(BaseModel):
    __tablename__ = "farmers"

    # --- Identity -------------------------------------------------------
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Optional — helps disambiguate farmers with similar names. Never a
    # required field: not every farmer knows or reports their DOB.
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    # E.164 format (e.g. +254712345678). Normalized BEFORE insert by the
    # service layer. This field is the SMS destination AND the anti-dup key.
    phone: Mapped[str] = mapped_column(String(20), nullable=False)

    # Optional because not all farmers have formal ID. Unique WHEN PRESENT —
    # Postgres unique constraints ignore NULLs, which is exactly what we want.
    national_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Lifecycle ------------------------------------------------------
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=FarmerStatus.PENDING_VERIFICATION.value,
        server_default=FarmerStatus.PENDING_VERIFICATION.value,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    # Self-referencing FK. When two farmer records turn out to be the same
    # person, the "loser" row points at the survivor.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=True
    )

    # --- Context (free-text only) ---------------------------------------
    # Deliberately free-text and NEVER used in filtering/reporting/logic.
    # Structured location will live on the Farm entity. This field exists
    # only so a clerk can jot a quick note during registration.
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Audit ----------------------------------------------------------
    # Who registered this farmer. Non-nullable — every farmer has a real
    # person behind them. This is our first line of defence against ghosts.
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Constraints ----------------------------------------------------
    __table_args__ = (
        UniqueConstraint("phone", name="uq_farmer_phone"),
        UniqueConstraint("national_id", name="uq_farmer_national_id"),
        # E.164: +, then 1-9 (no leading zero in country code), then 6-14 digits.
        CheckConstraint(
            r"phone ~ '^\+[1-9][0-9]{6,14}$'",
            name="ck_farmer_phone_e164",
        ),
        # A farmer cannot be merged into themselves.
        CheckConstraint(
            "merged_into_id IS NULL OR merged_into_id <> id",
            name="ck_farmer_no_self_merge",
        ),
        # status='merged' ⇔ merged_into_id IS NOT NULL (both directions).
        CheckConstraint(
            "(status = 'merged') = (merged_into_id IS NOT NULL)",
            name="ck_farmer_merge_consistency",
        ),
        # verified_at and verified_by_id set together or not at all.
        CheckConstraint(
            "(verified_at IS NULL) = (verified_by_id IS NULL)",
            name="ck_farmer_verification_consistency",
        ),
        # status must be one of the known values (mirrors FarmerStatus).
        CheckConstraint(
            "status IN (" + ", ".join(f"'{v}'" for v in FARMER_STATUS_VALUES) + ")",
            name="ck_farmer_status_valid",
        ),
        Index("ix_farmer_status", "status"),
        # List screens sort by newest first; without this every page scan+sort.
        # (Search indexes are trigram GINs, created in migration e52b47e5ff15
        # because they are expression indexes Alembic cannot mirror here.)
        Index("ix_farmer_created_at", "created_at"),
    )

    # --- Convenience ----------------------------------------------------
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Farmer {self.id} {self.full_name} ({self.status})>"
