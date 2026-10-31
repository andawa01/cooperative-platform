"""
Payment service.

Idempotency:
    Same idempotency_key + same request fingerprint → return existing payment.
    Same idempotency_key + different fingerprint   → 409 via IdempotencyConflict.
    New key                                        → create.

Allocation:
    Manual allocations come from the client and are validated atomically.
    If the client omits allocations, the service allocates FIFO against the
    farmer's oldest outstanding deliveries.

Concurrency:
    Every financial write takes the farmer-row lock (see D-010).

Cascade on reversal:
    Reversing a payment reverses all its non-reversed allocations in the
    same transaction. Same pattern as delivery reversal (D-019).
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import write_transaction
from app.models.delivery import Delivery
from app.models.farmer import Farmer
from app.models.payment import Payment, PaymentAllocation, PaymentStatus
from app.models.user import User
from app.schemas.payment import PaymentCreate
from app.services import audit

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class FarmerNotFound(Exception):
    pass


class PaymentNotFound(Exception):
    pass


class IdempotencyConflict(Exception):
    """Same idempotency key but different request fingerprint."""


class AllocationDeliveryNotFound(Exception):
    pass


class DuplicateAllocationDelivery(Exception):
    """Client sent two allocations targeting the same delivery."""


class AllocationExceedsRemaining(Exception):
    """Manual allocation exceeds the delivery's remaining unpaid value."""


class AllocationsExceedPayment(Exception):
    """Sum of manual allocations exceeds the payment amount."""


class PaymentAlreadyReversed(Exception):
    pass


class CannotReverseReversal(Exception):
    """Attempted to reverse a reversal row."""


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _fingerprint(data: PaymentCreate) -> str:
    """
    Deterministic hash of the semantically meaningful parts of a payment
    request. Used together with idempotency_key. Excludes the key itself
    (we're already keyed on it) and any client-side noise.
    """
    payload = {
        "farmer_id": str(data.farmer_id),
        "amount": str(data.amount),
        "currency": data.currency,
        "method": data.method.value,
        "reference": data.reference,
        "paid_at": data.paid_at.isoformat(),
        "allocations": (
            sorted(
                [
                    {"delivery_id": str(a.delivery_id), "amount": str(a.amount)}
                    for a in data.allocations
                ],
                key=lambda x: x["delivery_id"],
            )
            if data.allocations
            else None
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Remaining amounts
# ---------------------------------------------------------------------------


def _delivery_value(delivery: Delivery) -> Decimal:
    """Valued deliveries have amount = quantity * rate_snapshot."""
    if delivery.rate_snapshot is None:
        return Decimal("0")
    return delivery.quantity * delivery.rate_snapshot


def _net_allocated_for_delivery(db: Session, delivery_id: uuid.UUID) -> Decimal:
    """Sum of ALL allocations against this delivery, including reversals."""
    total = db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), Decimal("0"))).where(
            PaymentAllocation.delivery_id == delivery_id
        )
    )
    return total if total is not None else Decimal("0")


def _remaining_for_delivery(db: Session, delivery: Delivery) -> Decimal:
    """Value minus net-allocated, floored at 0 (defensive)."""
    remaining = _delivery_value(delivery) - _net_allocated_for_delivery(db, delivery.id)
    return remaining if remaining > 0 else Decimal("0")


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


def record_payment(
    db: Session,
    data: PaymentCreate,
    actor: User,
) -> tuple[Payment, bool]:
    """
    Record a payment.

    Returns (payment, replayed) — replayed=True if this was an idempotent
    replay of a previously-created payment.

    Raises IdempotencyConflict if the key matches but the fingerprint doesn't.
    Raises validation exceptions for manual-allocation problems.

    Note on transaction structure:
    The transaction opens FIRST, then the farmer lock, then the idempotency
    check. Placing the idempotency check inside the transaction (rather
    than as a fast-path pre-check) is both more correct under concurrency
    (two concurrent identical requests cannot both pass the pre-check) and
    necessary for the session state to be clean when `db.begin()` runs.
    """
    fingerprint = _fingerprint(data)

    with write_transaction(db):
        # Farmer lock: serialization point for all financial writes.
        farmer = db.scalar(
            select(Farmer).where(Farmer.id == data.farmer_id).with_for_update()
        )
        if farmer is None:
            raise FarmerNotFound()

        # Idempotency check inside the transaction. Two concurrent requests
        # with the same key serialize on the farmer lock; the second finds
        # the first's row and replays.
        existing = db.scalar(
            select(Payment).where(Payment.idempotency_key == data.idempotency_key)
        )
        if existing is not None:
            if existing.idempotency_fingerprint != fingerprint:
                raise IdempotencyConflict(
                    "idempotency key reused with a different request body"
                )
            return existing, True

        payment = Payment(
            farmer_id=data.farmer_id,
            amount=data.amount,
            currency=data.currency,
            method=data.method.value,
            reference=data.reference,
            paid_at=data.paid_at,
            recorded_at=datetime.now(UTC),
            recorded_by_id=actor.id,
            idempotency_key=data.idempotency_key,
            idempotency_fingerprint=fingerprint,
            status=PaymentStatus.CONFIRMED.value,
            reversal_of_id=None,
            notes=data.notes,
        )
        db.add(payment)
        db.flush()

        if data.allocations:
            _allocate_manual(db, payment, farmer, data.allocations)
        else:
            _allocate_fifo(db, payment, farmer)

        # Refresh INSIDE the transaction. A SELECT after the `with` block
        # would implicitly begin a new transaction, leaving the session
        # dirty and making the next `db.begin()` on it fail.
        db.refresh(payment)

        # No audit row on the idempotent-replay path above: nothing happened.
        # One payment, one entry — a replay must not look like a second event.
        # Allocations are summed in the same transaction so the payload
        # records how the money was actually split (the model has no
        # relationship to count from).
        alloc_count, alloc_sum = db.execute(
            select(
                func.count(PaymentAllocation.id),
                func.coalesce(func.sum(PaymentAllocation.amount), Decimal("0")),
            ).where(PaymentAllocation.payment_id == payment.id)
        ).one()
        audit.record(
            db,
            actor_id=actor.id,
            action="payment.create",
            entity_type="payment",
            entity_id=payment.id,
            after={
                "farmer_id": str(data.farmer_id),
                "amount": str(data.amount),
                "currency": data.currency,
                "method": data.method.value,
                "reference": data.reference,
                "paid_at": data.paid_at.isoformat(),
                "allocations": int(alloc_count),
                "allocated": str(alloc_sum),
                "unallocated_amount": str(data.amount - alloc_sum),
            },
        )

    return payment, False


def _allocate_manual(db: Session, payment: Payment, farmer: Farmer, allocations):
    """Validate + insert client-specified allocations."""
    # 1. No duplicate delivery_ids in the request.
    seen: set[uuid.UUID] = set()
    for a in allocations:
        if a.delivery_id in seen:
            raise DuplicateAllocationDelivery(
                f"delivery {a.delivery_id} appears more than once"
            )
        seen.add(a.delivery_id)

    # 2. Validate each allocation and compute total.
    total = Decimal("0")
    delivery_cache: dict[uuid.UUID, Delivery] = {}
    for a in allocations:
        d = db.get(Delivery, a.delivery_id)
        if d is None:
            raise AllocationDeliveryNotFound(f"delivery {a.delivery_id} not found")
        if d.farmer_id != farmer.id:
            raise AllocationDeliveryNotFound(
                f"delivery {a.delivery_id} does not belong to farmer"
            )
        if d.rate_snapshot is None:
            raise AllocationExceedsRemaining(
                f"delivery {a.delivery_id} has no value (pending valuation)"
            )
        if d.reversal_of_id is not None:
            raise AllocationExceedsRemaining(
                f"delivery {a.delivery_id} is a reversal row"
            )
        remaining = _remaining_for_delivery(db, d)
        if a.amount > remaining:
            raise AllocationExceedsRemaining(
                f"allocation {a.amount} exceeds remaining {remaining} "
                f"on delivery {a.delivery_id}"
            )
        delivery_cache[a.delivery_id] = d
        total += a.amount

    # 3. Total must not exceed payment amount.
    if total > payment.amount:
        raise AllocationsExceedPayment(
            f"allocations total {total} exceeds payment amount {payment.amount}"
        )

    # 4. Insert.
    for a in allocations:
        db.add(
            PaymentAllocation(
                payment_id=payment.id,
                delivery_id=a.delivery_id,
                amount=a.amount,
                reversal_of_id=None,
            )
        )


def _allocate_fifo(db: Session, payment: Payment, farmer: Farmer):
    """
    Greedy allocation, oldest outstanding deliveries first.

    Order: delivered_at ASC, id ASC (deterministic).
    Skips unvalued deliveries (they have no known remaining value).
    """
    # Lock all this farmer's non-reversal deliveries with a value.
    # (The farmer lock already serializes; we select without extra row locks.)
    deliveries = list(
        db.scalars(
            select(Delivery)
            .where(Delivery.farmer_id == farmer.id)
            .where(Delivery.rate_snapshot.is_not(None))
            .where(Delivery.reversal_of_id.is_(None))
            .order_by(Delivery.delivered_at.asc(), Delivery.id.asc())
        ).all()
    )

    remaining_payment = payment.amount
    for d in deliveries:
        if remaining_payment <= 0:
            break
        remaining_delivery = _remaining_for_delivery(db, d)
        if remaining_delivery <= 0:
            continue
        chunk = min(remaining_payment, remaining_delivery)
        db.add(
            PaymentAllocation(
                payment_id=payment.id,
                delivery_id=d.id,
                amount=chunk,
                reversal_of_id=None,
            )
        )
        remaining_payment -= chunk

    # Any leftover becomes unallocated credit on account. Nothing to insert.


# ---------------------------------------------------------------------------
# Reverse
# ---------------------------------------------------------------------------


def reverse_payment(
    db: Session,
    payment_id: uuid.UUID,
    reason: str,
    actor: User,
) -> Payment:
    """
    Reverse a payment: insert a negative payment row and reverse all its
    non-reversed allocations, in one transaction under the farmer lock.

    Original payment's status is NOT changed (see D-020).
    """
    with write_transaction(db):
        original = db.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if original is None:
            raise PaymentNotFound()
        if original.reversal_of_id is not None:
            raise CannotReverseReversal()

        already = db.scalar(
            select(Payment.id).where(Payment.reversal_of_id == original.id)
        )
        if already is not None:
            raise PaymentAlreadyReversed()

        # Farmer lock.
        db.execute(
            select(Farmer.id).where(Farmer.id == original.farmer_id).with_for_update()
        )

        reversal = Payment(
            farmer_id=original.farmer_id,
            amount=-original.amount,
            currency=original.currency,
            method=original.method,
            reference=original.reference,
            paid_at=original.paid_at,
            recorded_at=datetime.now(UTC),
            recorded_by_id=actor.id,
            idempotency_key=f"reversal:{original.id}",
            idempotency_fingerprint="0" * 64,  # marker; never matched as input
            status=PaymentStatus.CONFIRMED.value,
            reversal_of_id=original.id,
            notes=f"[reversal] {reason}",
        )
        db.add(reversal)
        db.flush()

        # Cascade allocations.
        allocations = list(
            db.scalars(
                select(PaymentAllocation)
                .where(PaymentAllocation.payment_id == original.id)
                .where(PaymentAllocation.reversal_of_id.is_(None))
            ).all()
        )
        for alloc in allocations:
            exists = db.scalar(
                select(PaymentAllocation.id).where(
                    PaymentAllocation.reversal_of_id == alloc.id
                )
            )
            if exists is not None:
                continue
            db.add(
                PaymentAllocation(
                    payment_id=reversal.id,
                    delivery_id=alloc.delivery_id,
                    amount=-alloc.amount,
                    reversal_of_id=alloc.id,
                )
            )

        db.refresh(reversal)

        # Subject is the original payment: that is what a person asks about.
        audit.record(
            db,
            actor_id=actor.id,
            action="payment.reverse",
            entity_type="payment",
            entity_id=original.id,
            before={
                "amount": str(original.amount),
                "currency": original.currency,
                "method": original.method,
                "status": original.status,
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


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_payment(db: Session, payment_id: uuid.UUID) -> Payment:
    p = db.get(Payment, payment_id)
    if p is None:
        raise PaymentNotFound()
    return p


def list_payments(
    db: Session,
    *,
    farmer_id: uuid.UUID | None = None,
    include_reversals: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Payment], int]:
    stmt = select(Payment)
    count_stmt = select(func.count()).select_from(Payment)
    conds = []
    if farmer_id is not None:
        conds.append(Payment.farmer_id == farmer_id)
    if not include_reversals:
        conds.append(Payment.reversal_of_id.is_(None))
    for c in conds:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)
    stmt = (
        stmt.order_by(Payment.paid_at.desc(), Payment.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all()), db.scalar(count_stmt) or 0


def allocation_state_for_payments(
    db: Session, payments: list[Payment]
) -> tuple[dict[uuid.UUID, list[PaymentAllocation]], dict[uuid.UUID, Decimal]]:
    """
    Allocations and net allocated totals for a whole page, in ONE query.

    A list screen needs two facts per payment: its allocation rows and their
    summed amount. The naive path asks the database for each separately, per
    row — 2N statements, so a 100-row page cost 201 queries. Both facts come
    from the same rows, so one query answers both.

    Returns ({payment_id: rows}, {payment_id: net}). Payments with no
    allocations appear in both maps with an empty list and zero, so callers
    never have to special-case them.
    """
    if not payments:
        return {}, {}

    ids = [p.id for p in payments]
    rows = db.scalars(
        select(PaymentAllocation)
        .where(PaymentAllocation.payment_id.in_(ids))
        .order_by(PaymentAllocation.created_at.asc())
    ).all()

    by_payment: dict[uuid.UUID, list[PaymentAllocation]] = {i: [] for i in ids}
    net: dict[uuid.UUID, Decimal] = {i: Decimal("0") for i in ids}
    for row in rows:
        by_payment[row.payment_id].append(row)
        net[row.payment_id] += row.amount
    return by_payment, net


def list_allocations_for_payment(db: Session, payment_id: uuid.UUID) -> list:
    return list(
        db.scalars(
            select(PaymentAllocation)
            .where(PaymentAllocation.payment_id == payment_id)
            .order_by(PaymentAllocation.created_at.asc())
        ).all()
    )
