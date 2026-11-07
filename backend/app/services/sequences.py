"""
Sequence allocation for quotable document numbers.

The only caller today is the delivery receipt (0.5). The rules that matter:

- The number is taken while holding a row lock on the counter, so two clerks
  recording deliveries at the same moment receive different numbers.
- It is taken inside the caller's transaction. If the delivery insert fails,
  the counter increment rolls back with it and no number is skipped.
- The counter is per calendar year of `delivered_at`, so a receipt reads with
  the season it belongs to and the number stays short.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.sequence import DocumentSequence

DELIVERY_RECEIPT = "delivery_receipt"


def next_delivery_receipt_number(db: Session, delivered_at: datetime) -> str:
    """Allocate the next receipt number for the delivery's year."""
    year = delivered_at.year
    seq = _lock_sequence(db, DELIVERY_RECEIPT, year)
    seq.last_value += 1
    # autoflush=False on these sessions: make the new value visible (and
    # durable within the transaction) before the caller commits.
    db.flush()
    return f"D-{year}-{seq.last_value:06d}"


def _lock_sequence(db: Session, name: str, year: int) -> DocumentSequence:
    """
    Return the locked counter row for (name, year), creating it if needed.

    The first document of a year has no row to lock, so two concurrent clerks
    can both try to insert one. The unique constraint decides; the loser
    locks the winner's row and continues. Without that, one of the two
    deliveries would fail for a reason that has nothing to do with it.
    """
    seq = _select_locked(db, name, year)
    if seq is not None:
        return seq

    try:
        with db.begin_nested():
            seq = DocumentSequence(name=name, year=year, last_value=0)
            db.add(seq)
            db.flush()
        return seq
    except IntegrityError:
        seq = _select_locked(db, name, year)
        if seq is None:  # pragma: no cover - only if the row vanished
            raise
        return seq


def _select_locked(db: Session, name: str, year: int) -> DocumentSequence | None:
    return db.scalar(
        select(DocumentSequence)
        .where(DocumentSequence.name == name)
        .where(DocumentSequence.year == year)
        .with_for_update()
    )
