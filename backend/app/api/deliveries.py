"""
Delivery and balance endpoints.

Permissions:
- Record delivery: admin + clerk
- List / read: admin + clerk
- Value (assign rate to pending): admin only
- Reverse: admin only
- Balance: admin + clerk
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.delivery import (
    BalanceResponse,
    DeliveryCreate,
    DeliveryListResponse,
    DeliveryResponse,
    DeliveryReverseRequest,
)
from app.services import delivery as delivery_service
from app.services import ledger as ledger_service
from app.services.delivery import (
    DeliveryAlreadyReversed,
    DeliveryNotFound,
    DeliveryNotValued,
    FarmerNotActive,
    FarmerNotFound,
    NoRateAvailableForValuation,
    ProduceLineInactive,
    ProduceLineNotFound,
)
from app.core.config import settings


router = APIRouter(tags=["deliveries"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, DeliveryNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
    if isinstance(exc, FarmerNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")
    if isinstance(exc, ProduceLineNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Produce line not found")
    if isinstance(exc, FarmerNotActive):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ProduceLineInactive):
        return HTTPException(status.HTTP_409_CONFLICT, "Produce line is inactive")
    if isinstance(exc, DeliveryAlreadyReversed):
        return HTTPException(status.HTTP_409_CONFLICT, "Delivery already reversed")
    if isinstance(exc, DeliveryNotValued):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, NoRateAvailableForValuation):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------

@router.post(
    "/deliveries",
    response_model=DeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def record_delivery(
    payload: DeliveryCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Record a delivery. Admin or clerk. Idempotency is the client's job."""
    try:
        return delivery_service.record_delivery(db, payload, actor)
    except (
        FarmerNotFound,
        ProduceLineNotFound,
        FarmerNotActive,
        ProduceLineInactive,
    ) as exc:
        raise _translate(exc)


@router.get("/deliveries", response_model=DeliveryListResponse)
def list_deliveries(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    farmer_id: uuid.UUID | None = Query(default=None),
    produce_line_id: uuid.UUID | None = Query(default=None),
    recorded_by_id: uuid.UUID | None = Query(default=None),
    delivered_from: datetime | None = Query(default=None),
    delivered_to: datetime | None = Query(default=None),
    include_reversals: bool = Query(default=False),
    unvalued_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = delivery_service.list_deliveries(
        db,
        farmer_id=farmer_id,
        produce_line_id=produce_line_id,
        recorded_by_id=recorded_by_id,
        delivered_from=delivered_from,
        delivered_to=delivered_to,
        include_reversals=include_reversals,
        unvalued_only=unvalued_only,
        limit=limit,
        offset=offset,
    )
    return DeliveryListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
def get_delivery(
    delivery_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return delivery_service.get_delivery(db, delivery_id)
    except DeliveryNotFound as exc:
        raise _translate(exc)


@router.post(
    "/deliveries/{delivery_id}/value",
    response_model=DeliveryResponse,
)
def value_delivery(
    delivery_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Value a previously unvalued delivery. Admin only. One-time operation.

    Looks up the rate effective on the delivery's delivered_at and snapshots
    it. Fails if no rate exists for that date.
    """
    try:
        return delivery_service.value_delivery(db, delivery_id, actor)
    except (
        DeliveryNotFound,
        DeliveryNotValued,
        NoRateAvailableForValuation,
    ) as exc:
        raise _translate(exc)


@router.post(
    "/deliveries/{delivery_id}/reverse",
    response_model=DeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def reverse_delivery(
    delivery_id: uuid.UUID,
    payload: DeliveryReverseRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Reverse a delivery. Admin only. Cascades to reverse the delivery's
    allocations in the same transaction. Returns the reversal row.
    """
    try:
        return delivery_service.reverse_delivery(db, delivery_id, payload.reason, actor)
    except (
        DeliveryNotFound,
        DeliveryAlreadyReversed,
        DeliveryNotValued,
    ) as exc:
        raise _translate(exc)


# ---------------------------------------------------------------------------
# Balance
# ---------------------------------------------------------------------------

@router.get(
    "/farmers/{farmer_id}/balance",
    response_model=BalanceResponse,
)
def get_farmer_balance(
    farmer_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Farmer's financial position derived from the ledger.

    Returns three distinct numbers (see D-019):
    - outstanding_debt: what the co-op still owes for deliveries
    - allocated_to_deliveries: informational; already reflected in debt
    - available_credit: money on account
    Plus a count of pending-valuation deliveries.
    """
    # Reuse the farmer existence check from the farmers service.
    from app.services import farmer as farmer_service
    from app.services.farmer import FarmerNotFound as FarmerSvcNotFound
    try:
        farmer_service.get_farmer(db, farmer_id)
    except FarmerSvcNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")

    bal = ledger_service.compute_balance(db, farmer_id)
    return BalanceResponse(
        farmer_id=farmer_id,
        currency=settings.default_currency,
        outstanding_debt=bal.outstanding_debt,
        allocated_to_deliveries=bal.allocated_to_deliveries,
        available_credit=bal.available_credit,
        pending_valuation_deliveries=bal.pending_valuation_deliveries,
    )