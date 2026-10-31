"""
Produce line and rate service.

The interesting part is `create_rate`. See DECISIONS.md D-018:

Rate changes are transactional and follow this protocol:
  1. Lock the produce line row (FOR UPDATE).
  2. Validate the requested effective_from.
  3. Find the currently-open rate (effective_to IS NULL) for this line.
  4. If the requested effective_from is after the current rate's start,
     close the current rate with effective_to = new effective_from.
     If it is before, reject: backdating a rate to before the previous
     rate started would require rewriting history (there's no earlier rate
     to close).
  5. Insert the new rate (open-ended).
  6. Count affected deliveries (informational).
  7. Commit atomically.

The exclusion constraint is the DB-level safety net. If our logic has a bug
or another code path writes directly, the constraint rejects overlapping
intervals.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.produce import ProduceLine, Rate
from app.models.user import User
from app.schemas.produce import ProduceLineCreate, ProduceLineUpdate, RateCreate
from app.services import audit

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class ProduceLineNotFound(Exception):
    pass


class ProduceLineCodeTaken(Exception):
    pass


class RateNotFound(Exception):
    pass


class RateOverlap(Exception):
    """Raised when a new rate would overlap an existing interval."""


class RateBackdatedBeforePrevious(Exception):
    """
    Raised when a requested effective_from precedes the current open rate's
    effective_from. We don't support rewriting that history.
    """


class ProduceLineInactive(Exception):
    """Raised when trying to set a rate on a deactivated produce line."""


# ---------------------------------------------------------------------------
# Produce lines
# ---------------------------------------------------------------------------


def create_produce_line(
    db: Session, data: ProduceLineCreate, actor: User
) -> ProduceLine:
    line = ProduceLine(
        code=data.code.strip().lower(),
        name=data.name.strip(),
        unit=data.unit.strip(),
        description=data.description,
        created_by_id=actor.id,
    )
    db.add(line)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProduceLineCodeTaken() from exc
    db.refresh(line)
    return line


def get_produce_line(db: Session, line_id: uuid.UUID) -> ProduceLine:
    line = db.get(ProduceLine, line_id)
    if line is None:
        raise ProduceLineNotFound()
    return line


def list_produce_lines(
    db: Session,
    *,
    include_inactive: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ProduceLine], int]:
    stmt = select(ProduceLine)
    count_stmt = select(func.count()).select_from(ProduceLine)

    if not include_inactive:
        stmt = stmt.where(ProduceLine.is_active.is_(True))
        count_stmt = count_stmt.where(ProduceLine.is_active.is_(True))

    stmt = stmt.order_by(ProduceLine.code.asc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), db.scalar(count_stmt) or 0


def update_produce_line(
    db: Session, line_id: uuid.UUID, data: ProduceLineUpdate
) -> ProduceLine:
    line = get_produce_line(db, line_id)
    updates = data.model_dump(exclude_unset=True)

    # Defense in depth: code and unit are not patchable.
    forbidden = {"code", "unit", "is_active"}
    if forbidden & set(updates):
        raise ValueError(f"fields not patchable: {forbidden & set(updates)}")

    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(line, key, value)

    db.commit()
    db.refresh(line)
    return line


def deactivate_produce_line(db: Session, line_id: uuid.UUID) -> ProduceLine:
    line = get_produce_line(db, line_id)
    if line.is_active:
        line.is_active = False
        db.commit()
        db.refresh(line)
    return line


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------


def _get_current_open_rate(db: Session, produce_line_id: uuid.UUID) -> Rate | None:
    """Return the rate with no effective_to for this produce line, if any."""
    return db.scalar(
        select(Rate)
        .where(Rate.produce_line_id == produce_line_id)
        .where(Rate.effective_to.is_(None))
    )


def create_rate(
    db: Session,
    produce_line_id: uuid.UUID,
    data: RateCreate,
    actor: User,
) -> tuple[Rate, Rate | None, int]:
    """
    Set a new rate for a produce line.

    Returns (new_rate, previous_rate, affected_deliveries_count).

    See module docstring for the protocol. The whole operation runs in a
    single transaction; the produce-line row is locked for the duration.
    """
    # Step 1: lock the produce line. This serializes concurrent rate changes
    # for the same line, giving us a predictable error rather than a race
    # against the exclusion constraint.
    line = db.scalar(
        select(ProduceLine).where(ProduceLine.id == produce_line_id).with_for_update()
    )
    if line is None:
        raise ProduceLineNotFound()

    if not line.is_active:
        raise ProduceLineInactive()

    # Step 2: find the current open rate (if any).
    current = _get_current_open_rate(db, produce_line_id)

    # Step 3: validate the requested effective_from against the timeline.
    if current is not None:
        if data.effective_from <= current.effective_from:
            raise RateBackdatedBeforePrevious(
                f"effective_from {data.effective_from} must be after the "
                f"current rate's effective_from {current.effective_from}"
            )
        # Close the current rate.
        current.effective_to = data.effective_from

    # Step 4: insert the new open rate.
    new_rate = Rate(
        produce_line_id=produce_line_id,
        rate_per_unit=data.rate_per_unit,
        currency=data.currency,
        effective_from=data.effective_from,
        effective_to=None,
        created_by_id=actor.id,
    )
    db.add(new_rate)

    # Step 5: count affected deliveries — informational only. We do NOT
    # rewrite their snapshots. Any correction is a separate, audited action.
    affected = (
        db.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.produce_line_id == produce_line_id)
            .where(
                Delivery.delivered_at
                >= datetime.combine(
                    data.effective_from, datetime.min.time(), tzinfo=UTC
                )
            )
            .where(Delivery.reversal_of_id.is_(None))
            .where(Delivery.rate_snapshot != data.rate_per_unit)
        )
        or 0
    )

    db.flush()  # assigns new_rate.id, which the audit entry needs

    # Pricing is money: recorded in the same transaction that closes the old
    # rate and opens the new one, so the trail can never disagree with the
    # rate table. The line the price applies to is in the payload, because
    # `entity_id` identifies the rate row itself.
    audit.record(
        db,
        actor_id=actor.id,
        action="rate.create",
        entity_type="rate",
        entity_id=new_rate.id,
        before=(
            {
                "rate_id": str(current.id),
                "rate_per_unit": str(current.rate_per_unit),
                "currency": current.currency,
                "effective_from": current.effective_from.isoformat(),
            }
            if current is not None
            else None
        ),
        after={
            "produce_line_id": str(produce_line_id),
            "rate_per_unit": str(data.rate_per_unit),
            "currency": data.currency,
            "effective_from": data.effective_from.isoformat(),
            "affected_deliveries": int(affected),
        },
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Should be unreachable given the lock + validation, but the DB is
        # the safety net. Translate cleanly rather than leak SQL details.
        raise RateOverlap(
            "rate overlaps an existing interval; this indicates a bug "
            "or a concurrent write outside the service"
        ) from exc

    db.refresh(new_rate)
    if current is not None:
        db.refresh(current)
    return new_rate, current, affected


def list_rates(db: Session, produce_line_id: uuid.UUID) -> list[Rate]:
    """Return the full rate history for a produce line, newest first."""
    get_produce_line(db, produce_line_id)  # 404 if line doesn't exist
    return list(
        db.scalars(
            select(Rate)
            .where(Rate.produce_line_id == produce_line_id)
            .order_by(Rate.effective_from.desc())
        ).all()
    )


def get_rate_at(db: Session, produce_line_id: uuid.UUID, on_date: date) -> Rate | None:
    """
    Return the rate in effect on a given date, or None if no rate covers it.
    Raises ProduceLineNotFound if the produce line doesn't exist.
    """
    get_produce_line(db, produce_line_id)
    return db.scalar(
        select(Rate)
        .where(Rate.produce_line_id == produce_line_id)
        .where(Rate.effective_from <= on_date)
        .where((Rate.effective_to.is_(None)) | (Rate.effective_to > on_date))
    )
