"""
Payment endpoints.

Permissions:
- record: admin + clerk
- list / read: admin + clerk
- reverse: admin only
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.farmer import Farmer
from app.models.user import User, UserRole
from app.schemas.payment import (
    AllocationResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentReverseRequest,
)
from app.services import notifications as notif_service
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
        return HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency key reused with different body",
        )
    if isinstance(exc, PaymentAlreadyReversed):
        return HTTPException(status.HTTP_409_CONFLICT, "Payment already reversed")
    if isinstance(exc, CannotReverseReversal):
        return HTTPException(status.HTTP_409_CONFLICT, "Cannot reverse a reversal")
    if isinstance(exc, DuplicateAllocationDelivery):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    if isinstance(exc, AllocationDeliveryNotFound):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    if isinstance(exc, AllocationExceedsRemaining):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    if isinstance(exc, AllocationsExceedPayment):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


def _serialize(
    db: Session,
    payment,
    farmer: Farmer | None = None,
    allocations: list | None = None,
    net_allocated: Decimal | None = None,
) -> PaymentResponse:
    """
    Build a PaymentResponse with its computed fields.

    Single-record endpoints let this function do the lookups. List endpoints
    pass `farmer`, `allocations` and `net_allocated` from their bulk queries,
    so rendering a page costs a fixed number of statements instead of two per
    row.
    """
    if farmer is None:
        farmer = db.get(Farmer, payment.farmer_id)
    if allocations is None:
        allocations = payment_service.list_allocations_for_payment(db, payment.id)
    if net_allocated is None:
        net_allocated = sum((a.amount for a in allocations), Decimal("0"))

    unalloc = payment.amount - net_allocated
    allocation_responses = [AllocationResponse.model_validate(a) for a in allocations]
    # Build a plain dict from the ORM object so we can inject the computed
    # fields (unallocated_amount, allocations) that are not DB columns.
    return PaymentResponse.model_validate(
        {
            "id": payment.id,
            "farmer_id": payment.farmer_id,
            "farmer_name": farmer.full_name if farmer else "Unknown farmer",
            "amount": payment.amount,
            "currency": payment.currency,
            "method": payment.method,
            "reference": payment.reference,
            "paid_at": payment.paid_at,
            "recorded_at": payment.recorded_at,
            "recorded_by_id": payment.recorded_by_id,
            "status": payment.status,
            "reversal_of_id": payment.reversal_of_id,
            "notes": payment.notes,
            "created_at": payment.created_at,
            "updated_at": payment.updated_at,
            "allocations": allocation_responses,
            "unallocated_amount": unalloc,
        }
    )


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

    # Only notify on the first successful creation, never on replay.
    if not replayed:
        try:
            notif_service.enqueue_payment_recorded(db, payment)
        except Exception:  # noqa: BLE001
            pass

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
        db,
        farmer_id=farmer_id,
        include_reversals=include_reversals,
        limit=limit,
        offset=offset,
    )

    # Bulk lookups for the whole page: names, allocations and their totals.
    farmer_ids = {p.farmer_id for p in items}
    farmers = (
        {f.id: f for f in db.scalars(select(Farmer).where(Farmer.id.in_(farmer_ids)))}
        if farmer_ids
        else {}
    )
    allocations, net_allocated = payment_service.allocation_state_for_payments(
        db, items
    )

    return PaymentListResponse(
        items=[
            _serialize(
                db,
                p,
                farmers.get(p.farmer_id),
                allocations.get(p.id, []),
                net_allocated.get(p.id, Decimal("0")),
            )
            for p in items
        ],
        total=total,
        limit=limit,
        offset=offset,
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


@router.post(
    "/{payment_id}/reverse",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_payment(
    payment_id: uuid.UUID,
    payload: PaymentReverseRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        reversal = payment_service.reverse_payment(
            db, payment_id, payload.reason, actor
        )
    except (PaymentNotFound, PaymentAlreadyReversed, CannotReverseReversal) as exc:
        raise _translate(exc)
    return _serialize(db, reversal)
