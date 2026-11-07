"""
Approval endpoints (D-038).

Admin only, all of them. A clerk can still record deliveries, payments and
deductions; what they cannot do is release a large correction or a payroll
run, and they cannot see the queue of people asking to.

The money endpoints themselves stay where they are — reversing a payment is
still `POST /payments/{id}/reverse`. When the amount crosses the threshold,
that endpoint refuses with 409 and `X-Approval-Required: true`, and the
request is created here.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.approval import ApprovalStatus
from app.models.user import User, UserRole
from app.schemas.approval import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalListResponse,
    ApprovalResponse,
)
from app.services import approval as approval_service
from app.services.approval import (
    ApprovalEntityNotFound,
    ApprovalNotFound,
    ApprovalNotPending,
    BelowThreshold,
    NoLongerApplies,
    SelfApproval,
    UnknownAction,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ApprovalNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Approval request not found")
    if isinstance(exc, ApprovalEntityNotFound):
        return HTTPException(
            status.HTTP_404_NOT_FOUND,
            "The payment, deduction or run this refers to no longer exists",
        )
    if isinstance(exc, UnknownAction):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "That action cannot be sent for approval",
        )
    if isinstance(exc, (ApprovalNotPending, SelfApproval, NoLongerApplies)):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, BelowThreshold):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


def _serialize_many(db: Session, approvals: list) -> list[ApprovalResponse]:
    """Resolve both names for the whole page in one query, never per row."""
    if not approvals:
        return []

    ids = {a.requested_by_id for a in approvals}
    ids |= {a.decided_by_id for a in approvals if a.decided_by_id}
    names = {
        u.id: u.full_name for u in db.scalars(select(User).where(User.id.in_(ids)))
    }

    return [
        ApprovalResponse(
            id=a.id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            amount=a.amount,
            currency=a.currency,
            summary=a.summary,
            reason=a.reason,
            status=a.status,
            requested_by_id=a.requested_by_id,
            requested_by_name=names.get(a.requested_by_id, "Unknown user"),
            decided_by_id=a.decided_by_id,
            decided_by_name=(names.get(a.decided_by_id) if a.decided_by_id else None),
            decided_at=a.decided_at,
            decision_note=a.decision_note,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in approvals
    ]


@router.post("", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
def request_approval(
    payload: ApprovalCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Ask a second admin to approve one money move.

    The amount and summary are derived from the subject, never from this
    body, so an approval cannot describe one figure and release another.
    Asking twice for the same pending subject returns the same request.
    """
    try:
        approval = approval_service.request_approval(
            db, payload.action, payload.entity_id, payload.reason, actor
        )
    except (ApprovalEntityNotFound, BelowThreshold, UnknownAction) as exc:
        raise _translate(exc)

    return _serialize_many(db, [approval])[0]


@router.get("", response_model=ApprovalListResponse)
def list_approvals(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = approval_service.list_approvals(
        db,
        status=approval_status.value if approval_status else None,
        limit=limit,
        offset=offset,
    )
    return ApprovalListResponse(
        items=_serialize_many(db, [row[0] for row in rows]),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Approve **and execute** the action, as the approving admin.

    The reversal or dispatch is recorded with this admin as its actor, so the
    audit trail shows who released the money, not just who asked.
    """
    try:
        approval = approval_service.decide(
            db, approval_id, approve=True, note=payload.note, actor=actor
        )
    except (
        ApprovalNotFound,
        ApprovalNotPending,
        SelfApproval,
        NoLongerApplies,
    ) as exc:
        raise _translate(exc)

    return _serialize_many(db, [approval])[0]


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """Reject the request. Nothing is executed; the note says why."""
    try:
        approval = approval_service.decide(
            db, approval_id, approve=False, note=payload.note, actor=actor
        )
    except (
        ApprovalNotFound,
        ApprovalNotPending,
        SelfApproval,
        NoLongerApplies,
    ) as exc:
        raise _translate(exc)

    return _serialize_many(db, [approval])[0]
