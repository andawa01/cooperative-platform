"""
Notification service.

Two-store design (see D-024):
- Postgres holds the durable Notification record.
- Redis holds the dispatch state (status, attempts, last_error, sent_at)
  as a HASH per notification, plus the queue itself.

Public API:
- enqueue_delivery_recorded(db, delivery) -> Notification | None
- enqueue_payment_recorded(db, payment) -> Notification | None
- enqueue_payment_advice(db, payment) -> Notification | None   (1.4 — with breakdown)
- get_dispatch_state(notification_id) -> dict
- list_notifications(db, ...) -> (rows, total)
- retry_notification(db, notification_id) -> bool

The enqueue functions are best-effort: if Redis is unreachable, we still
create the Postgres record (so the fact of "we intended to notify" is
preserved) and log the failure. An admin can retry the dispatch later.
"""

import logging
import uuid
from datetime import UTC, datetime

import redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.redis_client import redis_client
from app.models.deduction import Deduction
from app.models.delivery import Delivery
from app.models.farmer import Farmer
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationTemplate,
    RelatedEntityType,
)
from app.models.payment import Payment

log = logging.getLogger(__name__)


# Redis keys.
# - sms_queue: a LIST used as a FIFO. LPUSH / BRPOP (RPOPLPUSH-ish pattern).
# - sms_retry_queue: a SORTED SET scored by unix timestamp for backoff.
# - notification:{id}: a HASH with dispatch state.
QUEUE_KEY = "shambatrack:sms:queue"
RETRY_KEY = "shambatrack:sms:retry"
STATE_KEY_PREFIX = "shambatrack:notification:"


class NotificationNotFound(Exception):
    pass


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def _render_delivery_recorded(delivery: Delivery, farmer: Farmer) -> str:
    """
    Build the SMS content for a delivery confirmation.

    Kept simple and English-only for MVP. A real deployment would use
    templates with placeholders, but for now this is honest and readable.
    """
    # Produce line code is not on the delivery; caller fills what it can.
    # We use the produce_line_id's short prefix as a stand-in.
    qty = f"{delivery.quantity:.2f}".rstrip("0").rstrip(".")
    line_code = f"#{str(delivery.produce_line_id)[:4]}"
    # The receipt number is the point of the message: it is what the member
    # quotes when they question the weight or the rate.
    receipt = f" Receipt {delivery.receipt_number}." if delivery.receipt_number else ""
    return (
        f"ShambaTrack: {farmer.first_name}, delivery of {qty} "
        f"({line_code}) recorded.{receipt} Thank you."
    )


def _render_payment_recorded(payment: Payment, farmer: Farmer) -> str:
    amount = f"{payment.amount:.2f}".rstrip("0").rstrip(".")
    return (
        f"ShambaTrack: {farmer.first_name}, payment of {amount} "
        f"{payment.currency} received. Thank you."
    )


# How a payout rail reads in a message a member actually receives.
RAIL_LABELS = {
    "cash": "cash",
    "mobile_money": "M-Pesa",
    "bank_transfer": "bank transfer",
}

# At most this many reasons are named; the rest are folded into "other" so a
# member with eight charge types does not get a four-segment SMS.
MAX_NAMED_REASONS = 2


def _money(value) -> str:
    return f"{value:,.2f}"


def _deduction_breakdown(
    db: Session, farmer_id: uuid.UUID
) -> tuple[object, list[tuple[str, object]]]:
    """
    (total withheld, [(reason label, amount), ...]) for one member.

    Signed rows are summed with no filtering, so a reversed deduction drops
    out — the same rule the ledger uses. Reasons are ordered by size because
    the big one is the one the member is asking about.
    """
    rows = db.execute(
        select(
            Deduction.reason_code,
            func.coalesce(func.sum(Deduction.amount), 0),
        )
        .where(Deduction.farmer_id == farmer_id)
        .group_by(Deduction.reason_code)
        .order_by(func.coalesce(func.sum(Deduction.amount), 0).desc())
    ).all()

    total = sum((amount for _, amount in rows), 0)
    named = [
        (reason.replace("_", " "), amount)
        for reason, amount in rows[:MAX_NAMED_REASONS]
        if amount != 0
    ]
    rest = sum((amount for _, amount in rows[MAX_NAMED_REASONS:]), 0)
    if rest != 0:
        named.append(("other", rest))
    return total, named


def _render_payment_advice(db: Session, payment: Payment, farmer: Farmer) -> str:
    """
    The message a member needs to settle a dispute without visiting the office:
    what arrived, and what the cooperative took out before it arrived.

    Deliberately does not claim to reconcile against produce. The payment may
    be an advance, a partial settlement, or a payout run covering several
    deliveries; inventing a "gross" figure that happens to add up would be a
    plausible-looking lie. What is stated is verifiable: the amount sent, the
    rail, the run reference, and the withheld total with its largest reasons.
    """
    rail = RAIL_LABELS.get(payment.method, payment.method.replace("_", " "))
    ref = f" ({payment.reference})" if payment.reference else ""
    head = (
        f"ShambaTrack: {farmer.first_name}, {_money(payment.amount)} "
        f"{payment.currency} sent via {rail}{ref}."
    )

    total, named = _deduction_breakdown(db, farmer.id)
    if not total or not named:
        return f"{head} No deductions. Thank you."

    detail = ", ".join(f"{label} {_money(amount)}" for label, amount in named)
    return f"{head} Less deductions {_money(total)} ({detail}). Thank you."


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


def _state_key(notification_id: uuid.UUID) -> str:
    return f"{STATE_KEY_PREFIX}{notification_id}"


def _write_state(
    notification_id: uuid.UUID,
    *,
    status: str,
    attempts: int,
    last_error: str | None,
    sent_at: datetime | None,
) -> None:
    """Write the full dispatch state as a Redis HASH. Best-effort."""
    key = _state_key(notification_id)
    mapping = {
        "status": status,
        "attempts": str(attempts),
        "last_error": last_error or "",
        "sent_at": sent_at.isoformat() if sent_at else "",
    }
    redis_client.hset(key, mapping=mapping)


def get_dispatch_state(notification_id: uuid.UUID) -> dict:
    """
    Read the dispatch state. Returns a dict with sensible defaults if the
    key is missing (Redis down, or the notification was never enqueued).
    """
    try:
        raw = redis_client.hgetall(_state_key(notification_id))
    except redis.RedisError:
        return {
            "status": "unknown",
            "attempts": 0,
            "last_error": "redis unreachable",
            "sent_at": None,
        }

    if not raw:
        return {
            "status": "unknown",
            "attempts": 0,
            "last_error": "not enqueued",
            "sent_at": None,
        }

    sent_at_str = raw.get("sent_at") or None
    return {
        "status": raw.get("status", "unknown"),
        "attempts": int(raw.get("attempts", "0")),
        "last_error": raw.get("last_error") or None,
        "sent_at": datetime.fromisoformat(sent_at_str) if sent_at_str else None,
    }


def _enqueue(notification_id: uuid.UUID, delay_seconds: int = 0) -> bool:
    """
    Put a notification on the queue. delay_seconds > 0 pushes onto the
    retry sorted set (scored by future timestamp). Otherwise LPUSH onto
    the immediate queue.

    Returns True on success, False if Redis is unreachable.
    """
    try:
        if delay_seconds > 0:
            score = datetime.now(UTC).timestamp() + delay_seconds
            redis_client.zadd(RETRY_KEY, {str(notification_id): score})
        else:
            redis_client.lpush(QUEUE_KEY, str(notification_id))
        return True
    except redis.RedisError as exc:
        log.error("redis enqueue failed for notification %s: %s", notification_id, exc)
        return False


# ---------------------------------------------------------------------------
# Public: enqueue from delivery / payment recording
# ---------------------------------------------------------------------------


def _create_notification_row(
    db: Session,
    *,
    farmer_id: uuid.UUID,
    template: NotificationTemplate,
    recipient: str,
    content: str,
    related_type: RelatedEntityType,
    related_id: uuid.UUID,
) -> Notification:
    n = Notification(
        farmer_id=farmer_id,
        channel=NotificationChannel.SMS.value,
        template=template.value,
        recipient=recipient,
        content=content,
        related_entity_type=related_type.value,
        related_entity_id=related_id,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def enqueue_delivery_recorded(db: Session, delivery: Delivery) -> Notification | None:
    """
    Called after a delivery is recorded. Creates the durable Notification
    record and pushes it onto the Redis queue. Best-effort: if Redis is
    unreachable, the DB record still exists and the caller is not failed.
    """
    farmer = db.get(Farmer, delivery.farmer_id)
    if farmer is None:
        return None

    content = _render_delivery_recorded(delivery, farmer)
    n = _create_notification_row(
        db,
        farmer_id=farmer.id,
        template=NotificationTemplate.DELIVERY_RECORDED,
        recipient=farmer.phone,
        content=content,
        related_type=RelatedEntityType.DELIVERY,
        related_id=delivery.id,
    )

    enqueued = _enqueue(n.id)
    _write_state(
        n.id,
        status="queued",
        attempts=0,
        last_error=None if enqueued else "redis unreachable",
        sent_at=None,
    )
    return n


def enqueue_payment_advice(db: Session, payment: Payment) -> Notification | None:
    """
    Payment confirmation that shows its arithmetic (D-033).

    Used wherever money reaches a member and withholding may have happened —
    a payout run, a counter payment. Falls back to the plain wording when
    nothing was withheld, so a member with no deductions sees no noise.
    """
    farmer = db.get(Farmer, payment.farmer_id)
    if farmer is None:
        return None

    content = _render_payment_advice(db, payment, farmer)
    n = _create_notification_row(
        db,
        farmer_id=farmer.id,
        template=NotificationTemplate.PAYMENT_ADVICE,
        recipient=farmer.phone,
        content=content,
        related_type=RelatedEntityType.PAYMENT,
        related_id=payment.id,
    )

    enqueued = _enqueue(n.id)
    _write_state(
        n.id,
        status="queued",
        attempts=0,
        last_error=None if enqueued else "redis unreachable",
        sent_at=None,
    )
    return n


def enqueue_payment_recorded(db: Session, payment: Payment) -> Notification | None:
    farmer = db.get(Farmer, payment.farmer_id)
    if farmer is None:
        return None

    content = _render_payment_recorded(payment, farmer)
    n = _create_notification_row(
        db,
        farmer_id=farmer.id,
        template=NotificationTemplate.PAYMENT_RECORDED,
        recipient=farmer.phone,
        content=content,
        related_type=RelatedEntityType.PAYMENT,
        related_id=payment.id,
    )

    enqueued = _enqueue(n.id)
    _write_state(
        n.id,
        status="queued",
        attempts=0,
        last_error=None if enqueued else "redis unreachable",
        sent_at=None,
    )
    return n


# ---------------------------------------------------------------------------
# Public: reads
# ---------------------------------------------------------------------------


def list_notifications(
    db: Session,
    *,
    farmer_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notification], int]:
    stmt = select(Notification)
    count_stmt = select(func.count()).select_from(Notification)
    if farmer_id is not None:
        stmt = stmt.where(Notification.farmer_id == farmer_id)
        count_stmt = count_stmt.where(Notification.farmer_id == farmer_id)
    stmt = stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), db.scalar(count_stmt) or 0


def get_notification(db: Session, notification_id: uuid.UUID) -> Notification:
    n = db.get(Notification, notification_id)
    if n is None:
        raise NotificationNotFound()
    return n


# ---------------------------------------------------------------------------
# Public: retry (used by the API for admin recovery)
# ---------------------------------------------------------------------------


def retry_notification(db: Session, notification_id: uuid.UUID) -> Notification:
    """
    Re-enqueue a notification. Idempotent-ish: sets status back to queued
    and pushes onto the immediate queue. The worker will pick it up.

    Admin action — a failed notification that needs another attempt, or a
    queue item lost when Redis was down.
    """
    n = get_notification(db, notification_id)
    state = get_dispatch_state(notification_id)
    _enqueue(notification_id)
    _write_state(
        notification_id,
        status="queued",
        attempts=state["attempts"],  # keep history; worker increments
        last_error=state["last_error"],
        sent_at=state["sent_at"],
    )
    return n
