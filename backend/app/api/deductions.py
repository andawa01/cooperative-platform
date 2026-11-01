"""
Deduction endpoints.

Permissions mirror payments: a clerk records what the co-op withheld, only an
admin can reverse it. Recording is the field action; undoing it is the
supervisory one.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.csv import MAX_EXPORT_ROWS, csv_response
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.deduction import DeductionReason
from app.models.farmer import Farmer
from app.models.user import User, UserRole
from app.schemas.deduction import (
    DeductionCreate,
    DeductionListResponse,
    DeductionResponse,
    DeductionReverseRequest,
)
from app.services import deduction as deduction_service
from app.services.deduction import (
    CannotReverseReversal,
    DeductionAlreadyReversed,
    DeductionNotFound,
    FarmerNotFound,
)

router = APIRouter(prefix="/deductions", tags=["deductions"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, DeductionNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Deduction not found")
    if isinstance(exc, FarmerNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")
    if isinstance(exc, DeductionAlreadyReversed):
        return HTTPException(status.HTTP_409_CONFLICT, "Deduction already reversed")
    if isinstance(exc, CannotReverseReversal):
        return HTTPException(status.HTTP_409_CONFLICT, "Cannot reverse a reversal")
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


def _serialize_many(db: Session, deductions: list) -> list[DeductionResponse]:
    """
    Build responses with farmer names resolved in one query for the page.

    Same rule as every other list (D-027): a screen must not cost one lookup
    per row.
    """
    if not deductions:
        return []

    farmer_ids = {d.farmer_id for d in deductions}
    farmers = {
        f.id: f for f in db.scalars(select(Farmer).where(Farmer.id.in_(farmer_ids)))
    }

    return [
        DeductionResponse(
            id=d.id,
            farmer_id=d.farmer_id,
            farmer_name=(
                farmers[d.farmer_id].full_name
                if d.farmer_id in farmers
                else "Unknown farmer"
            ),
            amount=d.amount,
            currency=d.currency,
            reason_code=d.reason_code,
            reference=d.reference,
            applied_at=d.applied_at,
            recorded_at=d.recorded_at,
            recorded_by_id=d.recorded_by_id,
            reversal_of_id=d.reversal_of_id,
            notes=d.notes,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in deductions
    ]


@router.post("", response_model=DeductionResponse, status_code=status.HTTP_201_CREATED)
def record_deduction(
    payload: DeductionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Record a deduction against a member. Admin or clerk."""
    try:
        deduction = deduction_service.record_deduction(db, payload, actor)
    except FarmerNotFound as exc:
        raise _translate(exc)
    return _serialize_many(db, [deduction])[0]


@router.get("", response_model=DeductionListResponse)
def list_deductions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    farmer_id: uuid.UUID | None = Query(default=None),
    reason_code: DeductionReason | None = Query(default=None),
    include_reversals: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = deduction_service.list_deductions(
        db,
        farmer_id=farmer_id,
        reason_code=reason_code.value if reason_code else None,
        include_reversals=include_reversals,
        limit=limit,
        offset=offset,
    )
    return DeductionListResponse(
        items=_serialize_many(db, items), total=total, limit=limit, offset=offset
    )


@router.get("/export", response_class=Response)
def export_deductions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    farmer_id: uuid.UUID | None = Query(default=None),
    reason_code: DeductionReason | None = Query(default=None),
    include_reversals: bool = Query(default=False),
):
    """
    Deductions matching the current filter, as CSV.

    Declared before `/{deduction_id}` so the literal path wins over the UUID
    lookup.
    """
    items, _total = deduction_service.list_deductions(
        db,
        farmer_id=farmer_id,
        reason_code=reason_code.value if reason_code else None,
        include_reversals=include_reversals,
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )
    rows = _serialize_many(db, items)
    return csv_response(
        filename=f"deductions-{date.today().isoformat()}.csv",
        header=[
            "id",
            "applied_at",
            "farmer",
            "reason_code",
            "amount",
            "currency",
            "reference",
            "kind",
            "recorded_at",
            "notes",
        ],
        rows=[
            (
                d.id,
                d.applied_at,
                d.farmer_name,
                # The response model holds the enum; CSV wants the raw code.
                d.reason_code.value,
                d.amount,
                d.currency,
                d.reference,
                "reversal" if d.reversal_of_id else "deduction",
                d.recorded_at,
                d.notes,
            )
            for d in rows
        ],
    )


@router.get("/{deduction_id}", response_model=DeductionResponse)
def get_deduction(
    deduction_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        deduction = deduction_service.get_deduction(db, deduction_id)
    except DeductionNotFound as exc:
        raise _translate(exc)
    return _serialize_many(db, [deduction])[0]


@router.post(
    "/{deduction_id}/reverse",
    response_model=DeductionResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_deduction(
    deduction_id: uuid.UUID,
    payload: DeductionReverseRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """Reverse a deduction. Admin only. Returns the reversal row."""
    try:
        reversal = deduction_service.reverse_deduction(
            db, deduction_id, payload.reason, actor
        )
    except (
        DeductionNotFound,
        DeductionAlreadyReversed,
        CannotReverseReversal,
    ) as exc:
        raise _translate(exc)
    return _serialize_many(db, [reversal])[0]
