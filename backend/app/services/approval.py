"""
Maker-checker (D-038).

A single admin can reverse a payment, reverse a deduction, or dispatch a run
that pays everyone. Each of those is a legitimate task — and each is also the
exact shape of an insider loss. This module holds the second pair of eyes.

Three rules, and the rest follows:

1. **The threshold is data, not a policy comment.** `settings.maker_checker_threshold`
   is compared at request time and at execution time, so raising it is an env
   change, and lowering it does not retroactively bless pending requests.
2. **The request is a snapshot.** The amount and summary are captured when
   asked. An approver who sees "KES 25,000.00" is approving that number.
3. **Execution goes through the same service function as the direct path.**
   Approving calls `payment.reverse_payment` with the approver as the actor.
   There is no second write path, so allocation, locking, reversal shape and
   audit entries cannot drift between "done directly" and "done after
   approval".

The endpoint gate lives in the routers (`assert_not_gated`), because the
service functions are also called from places that must not re-check — most
importantly this module. A new money-moving endpoint must call it too; the
alternative (a flag threaded through the service) turns the control into
something a caller can switch off.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core.config import settings
from app.db.session import write_transaction
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.models.deduction import Deduction
from app.models.farmer import Farmer
from app.models.payment import Payment
from app.models.payout import PayoutBatch, PayoutItem, PayoutItemStatus
from app.models.user import User
from app.services import audit
from app.services import deduction as deduction_service
from app.services import payment as payment_service
from app.services import payout as payout_service

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class ApprovalNotFound(Exception):
    pass


class ApprovalNotPending(Exception):
    """The request was already approved or rejected."""


class SelfApproval(Exception):
    """The approver is the person who asked."""


class UnknownAction(Exception):
    """Not one of the actions this system is willing to gate."""


class ApprovalEntityNotFound(Exception):
    pass


class BelowThreshold(Exception):
    """Nothing to approve — the direct endpoint can do this one."""


class ApprovalRequired(Exception):
    """The direct endpoint refused because the amount crosses the limit."""


class NoLongerApplies(Exception):
    """The subject changed while the request was waiting."""


ACTION_MODELS = {
    "payment.reverse": Payment,
    "deduction.reverse": Deduction,
    "payout.dispatch": PayoutBatch,
}

ENTITY_TYPES = {
    "payment.reverse": "payment",
    "deduction.reverse": "deduction",
    "payout.dispatch": "payout",
}

LABELS = {
    "payment.reverse": "Reversing this payment",
    "deduction.reverse": "Reversing this deduction",
    "payout.dispatch": "Dispatching this payout run",
}


def threshold() -> Decimal:
    return settings.maker_checker_threshold


def is_gated(amount: Decimal | None) -> bool:
    """At or above the limit needs a second admin; below it does not."""
    return amount is not None and amount >= threshold()


def _gated_message(action: str, amount: Decimal, currency: str | None) -> str:
    money = f"{currency or settings.default_currency} {amount:,.2f}"
    limit = f"{currency or settings.default_currency} {threshold():,.2f}"
    return (
        f"{LABELS[action]} ({money}) is at or above the {limit} maker-checker "
        "limit. Request approval, then have a different admin approve it."
    )


# ---------------------------------------------------------------------------
# Describing the subject
# ---------------------------------------------------------------------------


def _describe(db: Session, action: str, entity) -> tuple[Decimal, str, str]:
    """The amount being released, its currency, and a one-line summary."""
    if action == "payment.reverse":
        farmer = db.get(Farmer, entity.farmer_id)
        name = farmer.full_name if farmer else "Unknown member"
        return (
            entity.amount,
            entity.currency,
            f"Reverse a {entity.currency} {entity.amount:,.2f} payment to {name}",
        )

    if action == "deduction.reverse":
        farmer = db.get(Farmer, entity.farmer_id)
        name = farmer.full_name if farmer else "Unknown member"
        return (
            entity.amount,
            entity.currency,
            f"Reverse a {entity.currency} {entity.amount:,.2f} "
            f"{entity.reason_code.replace('_', ' ')} deduction from {name}",
        )

    if action == "payout.dispatch":
        # Only what has not been paid is being released now. A retry of a
        # partly-paid run is a smaller number than the run total, and that is
        # the number the approver should see.
        total, count = db.execute(
            select(
                func.coalesce(
                    func.sum(PayoutItem.amount).filter(
                        PayoutItem.status != PayoutItemStatus.PAID.value
                    ),
                    0,
                ),
                func.count(PayoutItem.id).filter(
                    PayoutItem.status != PayoutItemStatus.PAID.value
                ),
            ).where(PayoutItem.batch_id == entity.id)
        ).one()
        amount = Decimal(str(total))
        members = int(count)
        return (
            amount,
            entity.currency,
            f"Dispatch {entity.reference or 'a payout run'} to {members} "
            f"member{'s' if members != 1 else ''}",
        )

    raise UnknownAction(action)


# ---------------------------------------------------------------------------
# The endpoint gate
# ---------------------------------------------------------------------------


def assert_not_gated(db: Session, action: str, entity_id: uuid.UUID) -> None:
    """
    Raise `ApprovalRequired` if this action is above the limit.

    A missing subject is not this function's problem: the endpoint's own
    service turns that into the usual 404.
    """
    model = ACTION_MODELS.get(action)
    if model is None:
        raise UnknownAction(action)

    entity = db.get(model, entity_id)
    if entity is None:
        return

    amount, currency, _summary = _describe(db, action, entity)
    if is_gated(amount):
        raise ApprovalRequired(_gated_message(action, amount, currency))


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


def request_approval(
    db: Session,
    action: str,
    entity_id: uuid.UUID,
    reason: str | None,
    actor: User,
) -> ApprovalRequest:
    """
    Queue a second-admin decision for one subject.

    Asking twice for the same pending subject returns the existing request
    rather than stacking duplicates: a retried click is not a second opinion.
    """
    if action not in ACTION_MODELS:
        raise UnknownAction(action)

    with write_transaction(db):
        entity = db.get(ACTION_MODELS[action], entity_id)
        if entity is None:
            raise ApprovalEntityNotFound()

        amount, currency, summary = _describe(db, action, entity)
        if not is_gated(amount):
            raise BelowThreshold(
                f"This {action.replace('.', ' ')} is below the "
                f"{currency} {threshold():,.2f} maker-checker limit, so it does "
                "not need a second admin — do it directly."
            )

        existing = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.action == action)
            .where(ApprovalRequest.entity_type == ENTITY_TYPES[action])
            .where(ApprovalRequest.entity_id == entity_id)
            .where(ApprovalRequest.status == ApprovalStatus.PENDING.value)
        )
        if existing is not None:
            return existing

        approval = ApprovalRequest(
            action=action,
            entity_type=ENTITY_TYPES[action],
            entity_id=entity_id,
            amount=amount,
            currency=currency,
            summary=summary,
            reason=reason,
            status=ApprovalStatus.PENDING.value,
            requested_by_id=actor.id,
        )
        db.add(approval)
        db.flush()

        audit.record(
            db,
            actor_id=actor.id,
            action="approval.request",
            entity_type="approval",
            entity_id=approval.id,
            after={
                "action": action,
                "subject_type": approval.entity_type,
                "subject_id": str(entity_id),
                "amount": str(amount),
                "currency": currency,
                "reason": reason,
            },
        )

        db.flush()
        db.refresh(approval)

    return approval


# ---------------------------------------------------------------------------
# Decide
# ---------------------------------------------------------------------------


def decide(
    db: Session,
    approval_id: uuid.UUID,
    *,
    approve: bool,
    note: str | None,
    actor: User,
) -> ApprovalRequest:
    """
    Approve (and execute) or reject one request.

    The lock-and-validate step is its own transaction, because the executed
    service function commits its own work. A crash between execution and the
    status update leaves a pending request whose subject is already settled —
    approving it again fails on the unique reversal and is recorded as no
    longer applicable, rather than moving money twice.
    """
    _lock_pending(db, approval_id, actor)

    if not approve:
        return _settle(db, approval_id, ApprovalStatus.REJECTED, actor, note)

    try:
        _execute(db, approval_id, actor)
    except (
        payment_service.PaymentNotFound,
        payment_service.PaymentAlreadyReversed,
        payment_service.CannotReverseReversal,
        deduction_service.DeductionNotFound,
        deduction_service.DeductionAlreadyReversed,
        deduction_service.CannotReverseReversal,
        payout_service.PayoutNotFound,
        payout_service.InvalidBatchState,
    ) as exc:
        reason = _reason_for(exc)
        _settle(
            db,
            approval_id,
            ApprovalStatus.REJECTED,
            actor,
            f"No longer applicable: {reason}",
        )
        raise NoLongerApplies(reason) from exc

    return _settle(db, approval_id, ApprovalStatus.APPROVED, actor, note)


def _reason_for(exc: Exception) -> str:
    """Turn the service's bare exceptions into something a screen can show."""
    if isinstance(exc, payment_service.PaymentNotFound):
        return "Payment not found"
    if isinstance(exc, payment_service.PaymentAlreadyReversed):
        return "Payment already reversed"
    if isinstance(exc, payment_service.CannotReverseReversal):
        return "Cannot reverse a reversal"
    if isinstance(exc, deduction_service.DeductionNotFound):
        return "Deduction not found"
    if isinstance(exc, deduction_service.DeductionAlreadyReversed):
        return "Deduction already reversed"
    if isinstance(exc, deduction_service.CannotReverseReversal):
        return "Cannot reverse a reversal"
    if isinstance(exc, payout_service.PayoutNotFound):
        return "Payout run not found"
    return str(exc) or "The action no longer applies"


def _lock_pending(db: Session, approval_id: uuid.UUID, actor: User) -> ApprovalRequest:
    with write_transaction(db):
        approval = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update()
        )
        if approval is None:
            raise ApprovalNotFound()
        if approval.status != ApprovalStatus.PENDING.value:
            raise ApprovalNotPending(f"This request was already {approval.status}.")
        if approval.requested_by_id == actor.id:
            raise SelfApproval("You requested this. A different admin must approve it.")
    return approval


def _execute(db: Session, approval_id: uuid.UUID, actor: User) -> None:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None:
        raise ApprovalNotFound()

    reason = approval.reason or f"Approved by {actor.full_name}"

    if approval.action == "payment.reverse":
        payment_service.reverse_payment(db, approval.entity_id, reason, actor)
    elif approval.action == "deduction.reverse":
        deduction_service.reverse_deduction(db, approval.entity_id, reason, actor)
    elif approval.action == "payout.dispatch":
        payout_service.dispatch_batch(db, approval.entity_id, actor)
    else:
        raise UnknownAction(approval.action)


def _settle(
    db: Session,
    approval_id: uuid.UUID,
    status: ApprovalStatus,
    actor: User,
    note: str | None,
) -> ApprovalRequest:
    with write_transaction(db):
        approval = db.scalar(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_id)
            .with_for_update()
        )
        if approval is None:
            raise ApprovalNotFound()
        if approval.status != ApprovalStatus.PENDING.value:
            raise ApprovalNotPending(f"This request was already {approval.status}.")

        approval.status = status.value
        approval.decided_by_id = actor.id
        approval.decided_at = datetime.now(UTC)
        approval.decision_note = note

        audit.record(
            db,
            actor_id=actor.id,
            action=(
                "approval.approve"
                if status is ApprovalStatus.APPROVED
                else "approval.reject"
            ),
            entity_type="approval",
            entity_id=approval.id,
            before={"status": ApprovalStatus.PENDING.value},
            after={
                "status": status.value,
                "action": approval.action,
                "subject_id": str(approval.entity_id),
                "note": note,
            },
        )

        db.flush()
        db.refresh(approval)

    return approval


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def list_approvals(
    db: Session,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[ApprovalRequest, str | None, str | None]], int]:
    """Newest first, with both names joined — no query per row (D-027)."""
    requester = aliased(User)
    decider = aliased(User)

    stmt = (
        select(ApprovalRequest, requester.full_name, decider.full_name)
        .join(requester, requester.id == ApprovalRequest.requested_by_id, isouter=True)
        .join(decider, decider.id == ApprovalRequest.decided_by_id, isouter=True)
    )
    count_stmt = select(func.count()).select_from(ApprovalRequest)

    if status is not None:
        stmt = stmt.where(ApprovalRequest.status == status)
        count_stmt = count_stmt.where(ApprovalRequest.status == status)

    stmt = (
        stmt.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(stmt).all()
    total = db.scalar(count_stmt) or 0
    return [(row[0], row[1], row[2]) for row in rows], total
