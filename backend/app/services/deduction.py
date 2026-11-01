"""
Deduction service.

Same shape as the payment service, minus allocation: a deduction is a single
signed row that names a farmer and a reason. There is nothing to allocate
against, so recording is one insert and reversal is one compensating insert.

Concurrency follows D-010's protocol: every write takes the farmer-row lock
first, because a deduction changes that farmer's financial position and must
serialize against payments, delivery reversals and other deductions.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import write_transaction
from app.models.deduction import Deduction
from app.models.farmer import Farmer
from app.models.user import User
from app.schemas.deduction import DeductionCreate
from app.services import audit

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class FarmerNotFound(Exception):
    pass


class DeductionNotFound(Exception):
    pass


class DeductionAlreadyReversed(Exception):
    pass


class CannotReverseReversal(Exception):
    """Attempted to reverse a reversal row."""


class AmountExceedsLimit(Exception):
    """A single deduction may not exceed the ledger's money ceiling."""


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


def record_deduction(db: Session, data: DeductionCreate, actor: User) -> Deduction:
    """
    Record a deduction against a member.

    Deliberately no idempotency key, matching deliveries (D-008): the client
    submits once and a retry is a visible duplicate a clerk can reverse. The
    audit row and the signed-row model make that recoverable, which is the
    trade-off this codebase already made for delivery entry.
    """
    with write_transaction(db):
        # Serialization point for every financial write on this farmer.
        farmer = db.scalar(
            select(Farmer).where(Farmer.id == data.farmer_id).with_for_update()
        )
        if farmer is None:
            raise FarmerNotFound()

        deduction = Deduction(
            farmer_id=data.farmer_id,
            amount=data.amount,
            currency=data.currency,
            reason_code=data.reason_code.value,
            reference=data.reference,
            applied_at=data.applied_at,
            recorded_at=datetime.now(UTC),
            recorded_by_id=actor.id,
            reversal_of_id=None,
            notes=data.notes,
        )
        db.add(deduction)
        db.flush()

        audit.record(
            db,
            actor_id=actor.id,
            action="deduction.create",
            entity_type="deduction",
            entity_id=deduction.id,
            after={
                "farmer_id": str(data.farmer_id),
                "farmer_name": farmer.full_name,
                "amount": str(data.amount),
                "currency": data.currency,
                "reason_code": data.reason_code.value,
                "reference": data.reference,
                "applied_at": data.applied_at.isoformat(),
            },
        )

        db.refresh(deduction)

    return deduction


# ---------------------------------------------------------------------------
# Reverse
# ---------------------------------------------------------------------------


def reverse_deduction(
    db: Session,
    deduction_id: uuid.UUID,
    reason: str,
    actor: User,
) -> Deduction:
    """
    Reverse a deduction by inserting a negative row that points at it.

    The original keeps its amount and stays visible: the history of a charge
    that was withdrawn is part of the record, not something to erase.
    """
    with write_transaction(db):
        original = db.scalar(
            select(Deduction).where(Deduction.id == deduction_id).with_for_update()
        )
        if original is None:
            raise DeductionNotFound()
        if original.reversal_of_id is not None:
            raise CannotReverseReversal()

        already = db.scalar(
            select(Deduction.id).where(Deduction.reversal_of_id == original.id)
        )
        if already is not None:
            raise DeductionAlreadyReversed()

        # Farmer lock after the row lock, matching the payment reversal order.
        db.execute(
            select(Farmer.id).where(Farmer.id == original.farmer_id).with_for_update()
        )

        reversal = Deduction(
            farmer_id=original.farmer_id,
            amount=-original.amount,
            currency=original.currency,
            reason_code=original.reason_code,
            reference=original.reference,
            # Corrections sit in the period they correct (D-019).
            applied_at=original.applied_at,
            recorded_at=datetime.now(UTC),
            recorded_by_id=actor.id,
            reversal_of_id=original.id,
            notes=f"[reversal] {reason}",
        )
        db.add(reversal)
        db.flush()

        audit.record(
            db,
            actor_id=actor.id,
            action="deduction.reverse",
            entity_type="deduction",
            entity_id=original.id,
            before={
                "amount": str(original.amount),
                "reason_code": original.reason_code,
                "reversed": False,
            },
            after={
                "reversal_id": str(reversal.id),
                "reason": reason,
                "reversed": True,
            },
        )

        db.refresh(reversal)

    return reversal


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_deduction(db: Session, deduction_id: uuid.UUID) -> Deduction:
    deduction = db.get(Deduction, deduction_id)
    if deduction is None:
        raise DeductionNotFound()
    return deduction


def list_deductions(
    db: Session,
    *,
    farmer_id: uuid.UUID | None = None,
    reason_code: str | None = None,
    include_reversals: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Deduction], int]:
    stmt = select(Deduction)
    count_stmt = select(func.count()).select_from(Deduction)
    conditions = []

    if farmer_id is not None:
        conditions.append(Deduction.farmer_id == farmer_id)
    if reason_code is not None:
        conditions.append(Deduction.reason_code == reason_code)
    if not include_reversals:
        conditions.append(Deduction.reversal_of_id.is_(None))

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    stmt = (
        stmt.order_by(Deduction.applied_at.desc(), Deduction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all()), db.scalar(count_stmt) or 0
