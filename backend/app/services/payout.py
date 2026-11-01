"""
Payout run service (D-032).

Lifecycle: draft → approved → dispatched, or draft/approved → cancelled.

The important part is what dispatch *does*: for each item it records an
ordinary `Payment` through the existing payment service, so allocation (FIFO),
the audit trail, the SMS queue and reversal all keep working without a second
implementation. A payout run is a schedule, not a parallel ledger.

Why the loop is not wrapped in one transaction: a run of 400 members must not
lose 399 good payments because number 400 hit a validation error. Each item
commits on its own, a failure is recorded on that item, and the run reports
paid/failed counts. Double-payment on a retry is prevented by deriving the
payment's idempotency key from the item id — a second dispatch replays instead
of paying twice.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import write_transaction
from app.models.farmer import Farmer, FarmerStatus
from app.models.payment import PaymentMethod
from app.models.payout import PayoutBatch, PayoutItem, PayoutItemStatus, PayoutStatus
from app.models.user import User
from app.schemas.payment import PaymentCreate
from app.schemas.payout import PayoutCreate
from app.services import audit
from app.services import ledger as ledger_service
from app.services import notifications as notif_service
from app.services import payment as payment_service


class PayoutNotFound(Exception):
    pass


class FarmerNotFound(Exception):
    pass


class NoPayableMembers(Exception):
    """Nothing to pay — the run would be an empty file."""


class InvalidBatchState(Exception):
    """The action does not apply to the batch's current status."""


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_batch(db: Session, data: PayoutCreate, actor: User) -> PayoutBatch:
    """
    Snapshot every included member's payable into a draft run.

    Candidates are read with `ledger.compute_balance` rather than a bespoke
    aggregate query: the ledger has exactly one definition of what a member is
    owed, and a second one here would be the first place the two could drift.
    That costs a handful of queries per member; for a cooperative of this size
    it is a walk, and the reversal trigger is recorded in D-032.
    """
    with write_transaction(db):
        if data.farmer_ids:
            farmers = list(
                db.scalars(select(Farmer).where(Farmer.id.in_(data.farmer_ids)))
            )
            if len(farmers) != len(set(data.farmer_ids)):
                raise FarmerNotFound()
        else:
            farmers = list(
                db.scalars(
                    select(Farmer).where(Farmer.status == FarmerStatus.ACTIVE.value)
                )
            )

        batch = PayoutBatch(
            reference=None,
            currency=settings.default_currency,
            method=data.method.value,
            status=PayoutStatus.DRAFT.value,
            notes=data.notes,
            created_by_id=actor.id,
        )
        db.add(batch)
        db.flush()
        # Embeds the row id: unique without a sequence table, quotable enough
        # to read down a phone line, and no lock contention between admins.
        batch.reference = f"RUN-{datetime.now(UTC).year}-{batch.id.hex[:6].upper()}"

        included = 0
        for farmer in farmers:
            payable = ledger_service.compute_balance(db, farmer.id).net_payable
            if payable <= 0:
                continue
            db.add(
                PayoutItem(
                    batch_id=batch.id,
                    farmer_id=farmer.id,
                    amount=payable,
                    currency=batch.currency,
                    status=PayoutItemStatus.PENDING.value,
                )
            )
            included += 1

        if included == 0:
            # Raising rolls the whole transaction back, so no empty run is
            # left behind for someone to approve by mistake.
            raise NoPayableMembers()

        db.flush()

        audit.record(
            db,
            actor_id=actor.id,
            action="payout.create",
            entity_type="payout",
            entity_id=batch.id,
            after={
                "reference": batch.reference,
                "members": included,
                "method": batch.method,
                "currency": batch.currency,
            },
        )

        db.flush()
        db.refresh(batch)

    return batch


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


def approve_batch(db: Session, batch_id: uuid.UUID, actor: User) -> PayoutBatch:
    """
    Move a draft to approved. Admin only, at the router.

    Separate from dispatch on purpose: the person who builds the run and the
    person who releases the money can be two different admins.
    """
    with write_transaction(db):
        batch = db.scalar(
            select(PayoutBatch).where(PayoutBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            raise PayoutNotFound()
        if batch.status != PayoutStatus.DRAFT.value:
            raise InvalidBatchState(
                f"Only a draft run can be approved (this one is {batch.status})"
            )

        batch.status = PayoutStatus.APPROVED.value
        batch.approved_by_id = actor.id
        batch.approved_at = datetime.now(UTC)

        audit.record(
            db,
            actor_id=actor.id,
            action="payout.approve",
            entity_type="payout",
            entity_id=batch.id,
            after={"reference": batch.reference, "status": batch.status},
        )

        # Flush before refresh: sessions here run with autoflush=False, so a
        # refresh would re-read the row and discard the status change we just
        # made in memory.
        db.flush()
        db.refresh(batch)

    return batch


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch_batch(
    db: Session, batch_id: uuid.UUID, actor: User
) -> tuple[PayoutBatch, int, int, int]:
    """
    Pay every pending or failed item. Returns (batch, paid, failed, pending).

    Idempotent per item: the payment's idempotency key is derived from the item
    id, so re-dispatching a run after a partial failure replays the payments
    that already succeeded instead of paying them again.
    """
    batch = db.get(PayoutBatch, batch_id)
    if batch is None:
        raise PayoutNotFound()
    if batch.status not in (PayoutStatus.APPROVED.value, PayoutStatus.DISPATCHED.value):
        raise InvalidBatchState(
            f"Approve the run before dispatching it (it is {batch.status})"
        )

    items = list(
        db.scalars(
            select(PayoutItem)
            .where(PayoutItem.batch_id == batch.id)
            .where(
                PayoutItem.status.in_(
                    [PayoutItemStatus.PENDING.value, PayoutItemStatus.FAILED.value]
                )
            )
            .order_by(PayoutItem.created_at, PayoutItem.id)
        )
    )

    paid = 0
    failed = 0

    for item in items:
        idempotency_key = f"payout-{batch.id.hex[:16]}-{item.id.hex[:16]}"
        try:
            payment, _replayed = payment_service.record_payment(
                db,
                PaymentCreate(
                    farmer_id=item.farmer_id,
                    amount=item.amount,
                    currency=item.currency,
                    method=PaymentMethod(batch.method),
                    # The run reference is the payment's reference: the bank
                    # file and the ledger line carry the same string.
                    reference=batch.reference,
                    paid_at=datetime.now(UTC),
                    idempotency_key=idempotency_key,
                    notes=f"Payout run {batch.reference}",
                ),
                actor,
            )
        except Exception as exc:  # noqa: BLE001 — one member must not stop the run
            _settle_item(db, item.id, PayoutItemStatus.FAILED, error=str(exc)[:500])
            failed += 1
            continue

        _settle_item(db, item.id, PayoutItemStatus.PAID, payment_id=payment.id)

        # The advice SMS goes through the existing queue so a member paid by a
        # run gets the same message as one paid at the counter.
        try:
            notif_service.enqueue_payment_recorded(db, payment)
        except Exception:  # noqa: BLE001
            pass

        paid += 1

    with write_transaction(db):
        fresh = db.scalar(
            select(PayoutBatch).where(PayoutBatch.id == batch.id).with_for_update()
        )
        if fresh is None:
            raise PayoutNotFound()
        fresh.status = PayoutStatus.DISPATCHED.value
        if fresh.dispatched_at is None:
            fresh.dispatched_at = datetime.now(UTC)

        audit.record(
            db,
            actor_id=actor.id,
            action="payout.dispatch",
            entity_type="payout",
            entity_id=fresh.id,
            after={
                "reference": fresh.reference,
                "paid": paid,
                "failed": failed,
            },
        )
        db.flush()
        db.refresh(fresh)

    pending = _count_items(db, batch.id, PayoutItemStatus.PENDING.value)
    return fresh, paid, failed, pending


def _settle_item(
    db: Session,
    item_id: uuid.UUID,
    status: PayoutItemStatus,
    *,
    payment_id: uuid.UUID | None = None,
    error: str | None = None,
) -> None:
    """
    Record what happened to one item, in its own small transaction.

    The item row is locked first so two concurrent dispatches of the same run
    cannot both leave a status behind; the payment idempotency key is the real
    guard against double payment, this only keeps the record truthful.
    """
    with write_transaction(db):
        item = db.scalar(
            select(PayoutItem).where(PayoutItem.id == item_id).with_for_update()
        )
        if item is None:
            return
        item.status = status.value
        item.payment_id = payment_id
        item.error = error if status is PayoutItemStatus.FAILED else None
        if status is PayoutItemStatus.PAID:
            item.dispatched_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def cancel_batch(db: Session, batch_id: uuid.UUID, actor: User) -> PayoutBatch:
    """
    Abandon a run that has not paid anyone.

    Money that has already moved is corrected by reversing the individual
    payments, not by cancelling the run — a cancelled batch must never imply
    that a payment it produced was withdrawn.
    """
    with write_transaction(db):
        batch = db.scalar(
            select(PayoutBatch).where(PayoutBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            raise PayoutNotFound()
        if batch.status == PayoutStatus.CANCELLED.value:
            raise InvalidBatchState("This run is already cancelled")
        if batch.status == PayoutStatus.DISPATCHED.value:
            raise InvalidBatchState(
                "A dispatched run cannot be cancelled — reverse the payments instead"
            )

        batch.status = PayoutStatus.CANCELLED.value

        for item in db.scalars(
            select(PayoutItem)
            .where(PayoutItem.batch_id == batch.id)
            .where(PayoutItem.status == PayoutItemStatus.PENDING.value)
            .with_for_update()
        ):
            item.status = PayoutItemStatus.CANCELLED.value

        audit.record(
            db,
            actor_id=actor.id,
            action="payout.cancel",
            entity_type="payout",
            entity_id=batch.id,
            after={"reference": batch.reference, "status": batch.status},
        )

        db.flush()
        db.refresh(batch)

    return batch


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_batch(db: Session, batch_id: uuid.UUID) -> PayoutBatch:
    batch = db.get(PayoutBatch, batch_id)
    if batch is None:
        raise PayoutNotFound()
    return batch


def list_batches(
    db: Session, *, limit: int = 20, offset: int = 0
) -> tuple[list[PayoutBatch], int]:
    stmt = (
        select(PayoutBatch)
        .order_by(PayoutBatch.created_at.desc(), PayoutBatch.id.desc())
        .limit(limit)
        .offset(offset)
    )
    total = db.scalar(select(func.count()).select_from(PayoutBatch)) or 0
    return list(db.scalars(stmt).all()), total


def list_items(db: Session, batch_id: uuid.UUID) -> list[PayoutItem]:
    return list(
        db.scalars(
            select(PayoutItem)
            .where(PayoutItem.batch_id == batch_id)
            .order_by(PayoutItem.created_at, PayoutItem.id)
        ).all()
    )


def batch_totals(
    db: Session, batch_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[Decimal, int, int, int]]:
    """
    (total_amount, item_count, paid_count, failed_count) per batch, in one
    query — a list screen must not cost a query per row (D-027).
    """
    if not batch_ids:
        return {}

    rows = db.execute(
        select(
            PayoutItem.batch_id,
            func.coalesce(func.sum(PayoutItem.amount), 0),
            func.count(PayoutItem.id),
            func.count(PayoutItem.id).filter(
                PayoutItem.status == PayoutItemStatus.PAID.value
            ),
            func.count(PayoutItem.id).filter(
                PayoutItem.status == PayoutItemStatus.FAILED.value
            ),
        )
        .where(PayoutItem.batch_id.in_(batch_ids))
        .group_by(PayoutItem.batch_id)
    ).all()

    return {
        batch_id: (Decimal(str(total)), count, paid, failed)
        for batch_id, total, count, paid, failed in rows
    }


def _count_items(db: Session, batch_id: uuid.UUID, status: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(PayoutItem)
            .where(PayoutItem.batch_id == batch_id)
            .where(PayoutItem.status == status)
        )
        or 0
    )
