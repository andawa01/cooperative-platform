"""
Payment endpoints.

Permissions:
- record: admin + clerk
- list / read: admin + clerk
- reverse: admin only
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.payment import (
    AllocationResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentReverseRequest,
)
from app.services import payment as payment_service
from app.services.payment import (
    AllocationDeliveryNotFound,
    AllocationExceedsRemaining,
    AllocationsExceedPayment,
    CannotReverseReversal,
    DuplicateAllocationDelivery,
    FarmerNotFound,
    IdempotencyConflict,
    PaymentAlreadyReversed,
    PaymentNotFound,
)


router = APIRouter(prefix="/payments", tags=["payments"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PaymentNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if isinstance(exc, FarmerNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")
    if isinstance(exc, IdempotencyConflict):
        return HTTPException(status.HTTP_409_CONFLICT, "Idempotency key reused with different body")
    if isinstance(exc, PaymentAlreadyReversed):
        return HTTPException(status.HTTP_409_CONFLICT, "Payment already reversed")
    if isinstance(exc, CannotReverseReversal):
        return HTTPException(status.HTTP_409_CONFLICT, "Cannot reverse a reversal")
    if isinstance(exc, DuplicateAllocationDelivery):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, AllocationDeliveryNotFound):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, AllocationExceedsRemaining):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if isinstance(exc, AllocationsExceedPayment):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


def _serialize(db: Session, payment) -> PaymentResponse:
    unalloc = payment_service.unallocated_amount(db, payment)
    allocations = [
        AllocationResponse.model_validate(a)
        for a in payment_service.list_allocations_for_payment(db, payment.id)
    ]
    resp = PaymentResponse.model_validate(payment)
    resp.allocations = allocations
    resp.unallocated_amount = unalloc
    return resp


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate,
    response: Response,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    try:
        payment, replayed = payment_service.record_payment(db, payload, actor)
    except (
        FarmerNotFound,
        IdempotencyConflict,
        DuplicateAllocationDelivery,
        AllocationDeliveryNotFound,
        AllocationExceedsRemaining,
        AllocationsExceedPayment,
    ) as exc:
        raise _translate(exc)

    if replayed:
        response.headers["Idempotency-Replayed"] = "true"

    return _serialize(db, payment)


@router.get("", response_model=PaymentListResponse)
def list_payments(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    farmer_id: uuid.UUID | None = Query(default=None),
    include_reversals: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = payment_service.list_payments(
        db, farmer_id=farmer_id, include_reversals=include_reversals,
        limit=limit, offset=offset,
    )
    return PaymentListResponse(
        items=[_serialize(db, p) for p in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        p = payment_service.get_payment(db, payment_id)
    except PaymentNotFound as exc:
        raise _translate(exc)
    return _serialize(db, p)


@router.post("/{payment_id}/reverse", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
def reverse_payment(
    payment_id: uuid.UUID,
    payload: PaymentReverseRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        reversal = payment_service.reverse_payment(db, payment_id, payload.reason, actor)
    except (PaymentNotFound, PaymentAlreadyReversed, CannotReverseReversal) as exc:
        raise _translate(exc)
    return _serialize(db, reversal)