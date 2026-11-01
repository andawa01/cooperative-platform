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
from collections.abc import Iterable
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.csv import MAX_EXPORT_ROWS, csv_response
from app.api.deps import get_current_user, require_role
from app.core.config import settings
from app.db.session import get_db
from app.models.farmer import Farmer
from app.models.produce import ProduceLine
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
from app.services import notifications as notif_service
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
# Serialization
# ---------------------------------------------------------------------------


def _serialize_many(
    db: Session, deliveries: Iterable[object]
) -> list[DeliveryResponse]:
    """
    Build DeliveryResponse objects with farmer and produce-line names.

    Names are resolved in two bulk queries for the whole page, never one
    query per row. The delivery table stores ids only (D-008), so this is
    where the display join happens.
    """
    rows = list(deliveries)
    if not rows:
        return []

    farmer_ids = {d.farmer_id for d in rows}
    line_ids = {d.produce_line_id for d in rows}

    farmers = {
        f.id: f for f in db.scalars(select(Farmer).where(Farmer.id.in_(farmer_ids)))
    }
    lines = {
        line.id: line
        for line in db.scalars(select(ProduceLine).where(ProduceLine.id.in_(line_ids)))
    }

    return [
        DeliveryResponse(
            id=d.id,
            farmer_id=d.farmer_id,
            produce_line_id=d.produce_line_id,
            farmer_name=(
                farmers[d.farmer_id].full_name
                if d.farmer_id in farmers
                else "Unknown farmer"
            ),
            produce_line_name=(
                lines[d.produce_line_id].name
                if d.produce_line_id in lines
                else "Unknown produce line"
            ),
            quantity=d.quantity,
            delivered_at=d.delivered_at,
            recorded_at=d.recorded_at,
            recorded_by_id=d.recorded_by_id,
            rate_snapshot=d.rate_snapshot,
            currency_snapshot=d.currency_snapshot,
            amount=d.amount,
            reversal_of_id=d.reversal_of_id,
            location=d.location,
            notes=d.notes,
            created_at=d.created_at,
            updated_at=d.updated_at,
        )
        for d in rows
    ]


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
        delivery = delivery_service.record_delivery(db, payload, actor)
    except (
        FarmerNotFound,
        ProduceLineNotFound,
        FarmerNotActive,
        ProduceLineInactive,
    ) as exc:
        raise _translate(exc)

    # Best-effort SMS notification. The delivery is committed regardless
    # of whether Redis is reachable; see D-024.
    try:
        notif_service.enqueue_delivery_recorded(db, delivery)
    except Exception:  # noqa: BLE001
        # Never let a notification failure hide a successful delivery.
        pass

    return _serialize_many(db, [delivery])[0]


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
    return DeliveryListResponse(
        items=_serialize_many(db, items), total=total, limit=limit, offset=offset
    )


@router.get("/deliveries/export", response_class=Response)
def export_deliveries(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    farmer_id: uuid.UUID | None = Query(default=None),
    produce_line_id: uuid.UUID | None = Query(default=None),
    recorded_by_id: uuid.UUID | None = Query(default=None),
    delivered_from: datetime | None = Query(default=None),
    delivered_to: datetime | None = Query(default=None),
    include_reversals: bool = Query(default=False),
    unvalued_only: bool = Query(default=False),
):
    """
    Deliveries matching the current filter, as CSV.

    Declared before `/deliveries/{delivery_id}` so the literal path wins over
    the UUID lookup. Names come from the same bulk join the list uses.
    """
    items, _total = delivery_service.list_deliveries(
        db,
        farmer_id=farmer_id,
        produce_line_id=produce_line_id,
        recorded_by_id=recorded_by_id,
        delivered_from=delivered_from,
        delivered_to=delivered_to,
        include_reversals=include_reversals,
        unvalued_only=unvalued_only,
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )
    rows = _serialize_many(db, items)
    return csv_response(
        filename=f"deliveries-{date.today().isoformat()}.csv",
        header=[
            "id",
            "delivered_at",
            "farmer",
            "produce_line",
            "quantity",
            "rate_snapshot",
            "amount",
            "currency",
            "kind",
            "recorded_at",
            "location",
            "notes",
        ],
        rows=[
            (
                d.id,
                d.delivered_at,
                d.farmer_name,
                d.produce_line_name,
                d.quantity,
                d.rate_snapshot,
                d.amount,
                d.currency_snapshot,
                "reversal" if d.reversal_of_id else "delivery",
                d.recorded_at,
                d.location,
                d.notes,
            )
            for d in rows
        ],
    )


@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
def get_delivery(
    delivery_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        delivery = delivery_service.get_delivery(db, delivery_id)
    except DeliveryNotFound as exc:
        raise _translate(exc)
    return _serialize_many(db, [delivery])[0]


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
        delivery = delivery_service.value_delivery(db, delivery_id, actor)
    except (
        DeliveryNotFound,
        DeliveryNotValued,
        NoRateAvailableForValuation,
    ) as exc:
        raise _translate(exc)
    return _serialize_many(db, [delivery])[0]


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
        reversal = delivery_service.reverse_delivery(
            db, delivery_id, payload.reason, actor
        )
    except (
        DeliveryNotFound,
        DeliveryAlreadyReversed,
        DeliveryNotValued,
    ) as exc:
        raise _translate(exc)
    return _serialize_many(db, [reversal])[0]


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
