"""
Delivery service — recording, valuing, reversing.

Design context (see D-008, D-010, D-019):
- A delivery is an immutable factual record.
- Corrections are reversals (negative-quantity rows in the same table).
- Deliveries with no applicable rate at delivered_at are recorded with
  rate_snapshot = NULL ("pending valuation") and can be valued later via
  a one-time, audited operation.
- Reversing a delivery cascades to reverse its allocations in the same
  transaction. This keeps the ledger internally consistent.

Concurrency:
- Recording a delivery is not financial — it does not take the farmer
  lock. Two clerks can record concurrently.
- Reversing a delivery IS financial (it changes the farmer's debt and
  can create credit-on-account). We take the farmer-row lock per D-010.
- Valuing a pending delivery IS financial. Same lock.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import write_transaction
from app.models.delivery import Delivery
from app.models.farmer import Farmer, FarmerStatus
from app.models.payment import PaymentAllocation
from app.models.produce import ProduceLine, Rate
from app.models.user import User
from app.schemas.delivery import DeliveryCreate
from app.services import audit

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class DeliveryNotFound(Exception):
    pass


class FarmerNotFound(Exception):
    pass


class ProduceLineNotFound(Exception):
    pass


class FarmerNotActive(Exception):
    """Farmer is not in a state that allows new deliveries."""


class ProduceLineInactive(Exception):
    """Produce line is inactive."""


class DeliveryNotValued(Exception):
    """Attempted to reverse an unvalued delivery, or a similar state error."""


class DeliveryAlreadyReversed(Exception):
    """Attempted to reverse a delivery that has already been reversed."""


class NoRateAvailableForValuation(Exception):
    """Cannot value a delivery because no rate applies to its delivered_at."""


# ---------------------------------------------------------------------------
# Rate lookup
# ---------------------------------------------------------------------------


def _find_rate_for(db: Session, produce_line_id: uuid.UUID, on_date) -> Rate | None:
    """
    Return the Rate in effect on the given date for this produce line.

    Half-open interval [effective_from, effective_to). See D-007.
    """
    return db.scalar(
        select(Rate)
        .where(Rate.produce_line_id == produce_line_id)
        .where(Rate.effective_from <= on_date)
        .where((Rate.effective_to.is_(None)) | (Rate.effective_to > on_date))
    )


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


def record_delivery(
    db: Session,
    data: DeliveryCreate,
    actor: User,
) -> Delivery:
    """
    Record a new delivery.

    - Farmer must exist and be active (not pending_verification, suspended,
      archived, or merged).
    - Produce line must exist and be active.
    - The rate effective on data.delivered_at is snapshotted into the row.
      If no rate exists, rate_snapshot = NULL (pending valuation).
    - The currency defaults to the produce line's most recent rate currency,
      or, if none has ever existed, to the system default currency.
    """
    # Farmer state check.
    farmer = db.get(Farmer, data.farmer_id)
    if farmer is None:
        raise FarmerNotFound()
    if farmer.status != FarmerStatus.ACTIVE.value:
        raise FarmerNotActive(f"farmer is {farmer.status}, cannot receive deliveries")

    # Produce line state check.
    line = db.get(ProduceLine, data.produce_line_id)
    if line is None:
        raise ProduceLineNotFound()
    if not line.is_active:
        raise ProduceLineInactive()

    # Rate lookup at delivered_at.
    delivered_date = data.delivered_at.date()
    rate = _find_rate_for(db, data.produce_line_id, delivered_date)

    # Currency: from the matched rate, or the most recent rate ever set on
    # the line, or the system default. Currency is required by the schema.
    if rate is not None:
        currency = rate.currency
        rate_value = rate.rate_per_unit
    else:
        latest = db.scalar(
            select(Rate)
            .where(Rate.produce_line_id == data.produce_line_id)
            .order_by(Rate.effective_from.desc())
            .limit(1)
        )
        currency = latest.currency if latest is not None else settings.default_currency
        rate_value = None

    delivery = Delivery(
        farmer_id=data.farmer_id,
        produce_line_id=data.produce_line_id,
        quantity=data.quantity,
        delivered_at=data.delivered_at,
        recorded_at=datetime.now(UTC),
        recorded_by_id=actor.id,
        rate_snapshot=rate_value,
        currency_snapshot=currency,
        reversal_of_id=None,
        location=data.location,
        notes=data.notes,
    )
    db.add(delivery)
    db.flush()
    # Refresh before committing: a SELECT after commit would implicitly
    # begin a new transaction and leave the session dirty for the caller.
    db.refresh(delivery)

    # Same transaction as the insert: either both rows land or neither does.
    audit.record(
        db,
        actor_id=actor.id,
        action="delivery.create",
        entity_type="delivery",
        entity_id=delivery.id,
        after={
            "farmer_id": str(data.farmer_id),
            "produce_line_id": str(data.produce_line_id),
            "quantity": str(data.quantity),
            "delivered_at": data.delivered_at.isoformat(),
            "rate_snapshot": (str(rate_value) if rate_value is not None else None),
            "currency": currency,
            "pending_valuation": rate_value is None,
        },
    )
    db.commit()
    return delivery


# ---------------------------------------------------------------------------
# List / read
# ---------------------------------------------------------------------------


def get_delivery(db: Session, delivery_id: uuid.UUID) -> Delivery:
    d = db.get(Delivery, delivery_id)
    if d is None:
        raise DeliveryNotFound()
    return d


def list_deliveries(
    db: Session,
    *,
    farmer_id: uuid.UUID | None = None,
    produce_line_id: uuid.UUID | None = None,
    recorded_by_id: uuid.UUID | None = None,
    delivered_from: datetime | None = None,
    delivered_to: datetime | None = None,
    include_reversals: bool = False,
    unvalued_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Delivery], int]:
    """
    List deliveries with filters.

    Default (include_reversals=False) returns only normal deliveries — the
    ones a clerk records. Set include_reversals=True to include the negative
    reversal rows as well (for reconciliation views).

    unvalued_only=True returns only deliveries with rate_snapshot IS NULL,
    for the admin valuation workflow.
    """
    stmt = select(Delivery)
    count_stmt = select(func.count()).select_from(Delivery)

    conditions = []
    if farmer_id is not None:
        conditions.append(Delivery.farmer_id == farmer_id)
    if produce_line_id is not None:
        conditions.append(Delivery.produce_line_id == produce_line_id)
    if recorded_by_id is not None:
        conditions.append(Delivery.recorded_by_id == recorded_by_id)
    if delivered_from is not None:
        conditions.append(Delivery.delivered_at >= delivered_from)
    if delivered_to is not None:
        conditions.append(Delivery.delivered_at < delivered_to)
    if not include_reversals:
        conditions.append(Delivery.reversal_of_id.is_(None))
    if unvalued_only:
        conditions.append(Delivery.rate_snapshot.is_(None))
        # An unvalued delivery is never a reversal, but assert it for clarity.
        conditions.append(Delivery.reversal_of_id.is_(None))

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    stmt = (
        stmt.order_by(Delivery.delivered_at.desc(), Delivery.id.desc())
        .limit(limit)
        .offset(offset)
    )

    return list(db.scalars(stmt).all()), db.scalar(count_stmt) or 0


# ---------------------------------------------------------------------------
# Value (one-time, audited)
# ---------------------------------------------------------------------------


def value_delivery(
    db: Session,
    delivery_id: uuid.UUID,
    actor: User,
) -> Delivery:
    """
    Value a delivery that was recorded without an applicable rate.

    This is a documented, one-time write to an otherwise immutable row
    (see D-019). It is only permitted when rate_snapshot IS NULL.

    Takes the farmer-row lock to serialize against concurrent reversals or
    other financial writes.
    """
    with write_transaction(db):
        delivery = db.scalar(
            select(Delivery).where(Delivery.id == delivery_id).with_for_update()
        )
        if delivery is None:
            raise DeliveryNotFound()

        if delivery.rate_snapshot is not None:
            # Already valued — idempotent no-op.
            return delivery

        if delivery.reversal_of_id is not None:
            raise DeliveryNotValued("cannot value a reversal row")

        # Captured before the mutation so `before` describes the row as it
        # was, not as it ends up.
        previous_currency = delivery.currency_snapshot

        # Take the farmer lock before mutating financial state.
        db.execute(
            select(Farmer.id).where(Farmer.id == delivery.farmer_id).with_for_update()
        )

        rate = _find_rate_for(
            db, delivery.produce_line_id, delivery.delivered_at.date()
        )
        if rate is None:
            raise NoRateAvailableForValuation(
                "no rate applies to this delivery's delivered_at"
            )

        delivery.rate_snapshot = rate.rate_per_unit
        delivery.currency_snapshot = rate.currency

        # Flush, do NOT refresh. Sessions here run with autoflush=False, so a
        # `db.refresh()` at this point would SELECT the still-unflushed row and
        # expire the assignment above — silently discarding the valuation.
        db.flush()

        audit.record(
            db,
            actor_id=actor.id,
            action="delivery.value",
            entity_type="delivery",
            entity_id=delivery.id,
            before={
                "rate_snapshot": None,
                "currency": previous_currency,
            },
            after={
                "rate_snapshot": str(rate.rate_per_unit),
                "currency": rate.currency,
                "delivered_at": delivery.delivered_at.isoformat(),
            },
        )

    return delivery


# ---------------------------------------------------------------------------
# Reverse (cascades allocations, same transaction)
# ---------------------------------------------------------------------------


def reverse_delivery(
    db: Session,
    delivery_id: uuid.UUID,
    reason: str,
    actor: User,
) -> Delivery:
    """
    Reverse a delivery. Creates a compensating row with negative quantity
    and reverses the delivery's allocations in the same transaction.

    Takes the farmer-row lock.

    Returns the new reversal row. Callers usually don't need the original.
    """
    with write_transaction(db):
        original = db.scalar(
            select(Delivery).where(Delivery.id == delivery_id).with_for_update()
        )
        if original is None:
            raise DeliveryNotFound()

        if original.reversal_of_id is not None:
            raise DeliveryNotValued("cannot reverse a reversal row")

        # Has it already been reversed?
        existing = db.scalar(
            select(Delivery.id).where(Delivery.reversal_of_id == original.id)
        )
        if existing is not None:
            raise DeliveryAlreadyReversed()

        if original.rate_snapshot is None:
            raise DeliveryNotValued("cannot reverse an unvalued delivery")

        # Farmer lock (see D-010).
        db.execute(
            select(Farmer.id).where(Farmer.id == original.farmer_id).with_for_update()
        )

        reversal = Delivery(
            farmer_id=original.farmer_id,
            produce_line_id=original.produce_line_id,
            quantity=-original.quantity,
            # Inherited timestamp: reconciliation anchor, NOT a second
            # physical event (see D-019).
            delivered_at=original.delivered_at,
            recorded_at=datetime.now(UTC),
            recorded_by_id=actor.id,
            rate_snapshot=original.rate_snapshot,
            currency_snapshot=original.currency_snapshot,
            reversal_of_id=original.id,
            location=original.location,
            notes=f"[reversal] {reason}",
        )
        db.add(reversal)

        # Cascade: reverse every non-reversed allocation against this delivery.
        allocations = list(
            db.scalars(
                select(PaymentAllocation)
                .where(PaymentAllocation.delivery_id == original.id)
                .where(PaymentAllocation.reversal_of_id.is_(None))
            ).all()
        )
        for alloc in allocations:
            # Skip allocations that already have a reversal (defensive).
            already = db.scalar(
                select(PaymentAllocation.id).where(
                    PaymentAllocation.reversal_of_id == alloc.id
                )
            )
            if already is not None:
                continue
            reversal_alloc = PaymentAllocation(
                payment_id=alloc.payment_id,
                delivery_id=alloc.delivery_id,
                amount=-alloc.amount,
                reversal_of_id=alloc.id,
            )
            db.add(reversal_alloc)

        db.flush()
        db.refresh(reversal)

        # The subject is the ORIGINAL delivery — that is the row a person
        # asks about later. The reversal row's id is in the payload.
        audit.record(
            db,
            actor_id=actor.id,
            action="delivery.reverse",
            entity_type="delivery",
            entity_id=original.id,
            before={
                "quantity": str(original.quantity),
                "rate_snapshot": str(original.rate_snapshot),
                "amount": (
                    str(original.quantity * original.rate_snapshot)
                    if original.rate_snapshot is not None
                    else None
                ),
                "reversed": False,
            },
            after={
                "reversal_id": str(reversal.id),
                "reason": reason,
                "reversed": True,
                "reversed_allocations": len(allocations),
            },
        )

    return reversal
