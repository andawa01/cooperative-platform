"""
Payout run endpoints.

Permissions:
- create / approve / dispatch / cancel: admin only. This releases money for
  every member at once, which is not a clerk's call.
- list / read / export: admin + clerk, so the counter can answer "have I been
  paid yet?" without asking an admin.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.csv import MAX_EXPORT_ROWS, csv_response
from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.farmer import Farmer
from app.models.payout import PayoutBatch, PayoutItem
from app.models.user import User, UserRole
from app.schemas.payout import (
    PayoutBatchDetail,
    PayoutBatchResponse,
    PayoutCreate,
    PayoutDispatchResult,
    PayoutItemResponse,
    PayoutListResponse,
)
from app.services import payout as payout_service
from app.services import rails as rail_service
from app.services.payout import (
    FarmerNotFound,
    InvalidBatchState,
    NoPayableMembers,
    PayoutNotFound,
)

router = APIRouter(prefix="/payout-runs", tags=["payouts"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, PayoutNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Payout run not found")
    if isinstance(exc, FarmerNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")
    if isinstance(exc, NoPayableMembers):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            "No members have a positive payable — there is nothing to pay",
        )
    if isinstance(exc, InvalidBatchState):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


def _serialize_batch(batch: PayoutBatch, totals: tuple[Decimal, int, int, int]):
    total, count, paid, failed = totals
    return PayoutBatchResponse(
        id=batch.id,
        reference=batch.reference,
        currency=batch.currency,
        method=batch.method,
        status=batch.status,
        notes=batch.notes,
        created_by_id=batch.created_by_id,
        approved_by_id=batch.approved_by_id,
        approved_at=batch.approved_at,
        dispatched_at=batch.dispatched_at,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        total_amount=total,
        item_count=count,
        paid_count=paid,
        failed_count=failed,
    )


def _serialize_items(db: Session, items: list[PayoutItem]) -> list[PayoutItemResponse]:
    """Farmer names and phones resolved in one query for the whole run."""
    if not items:
        return []

    farmer_ids = {item.farmer_id for item in items}
    farmers = {
        f.id: f for f in db.scalars(select(Farmer).where(Farmer.id.in_(farmer_ids)))
    }

    responses: list[PayoutItemResponse] = []
    for item in items:
        farmer = farmers.get(item.farmer_id)
        responses.append(
            PayoutItemResponse(
                id=item.id,
                farmer_id=item.farmer_id,
                farmer_name=farmer.full_name if farmer else "Unknown farmer",
                phone=farmer.phone if farmer else None,
                amount=item.amount,
                currency=item.currency,
                status=item.status,
                payment_id=item.payment_id,
                error=item.error,
                dispatched_at=item.dispatched_at,
            )
        )
    return responses


@router.post("", response_model=PayoutBatchDetail, status_code=status.HTTP_201_CREATED)
def create_payout_run(
    payload: PayoutCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Create a draft run from each included member's current payable.

    The amounts are frozen here. Recording a deduction after this point changes
    the member's balance but not this run — an amount already promised must not
    move underneath the person who promised it.
    """
    try:
        batch = payout_service.create_batch(db, payload, actor)
    except (FarmerNotFound, NoPayableMembers) as exc:
        raise _translate(exc)

    items = payout_service.list_items(db, batch.id)
    totals = payout_service.batch_totals(db, [batch.id]).get(
        batch.id, (Decimal("0"), 0, 0, 0)
    )
    return PayoutBatchDetail(
        **_serialize_batch(batch, totals).model_dump(),
        items=_serialize_items(db, items),
    )


@router.get("", response_model=PayoutListResponse)
def list_payout_runs(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    batches, total = payout_service.list_batches(db, limit=limit, offset=offset)
    totals = payout_service.batch_totals(db, [b.id for b in batches])
    return PayoutListResponse(
        items=[
            _serialize_batch(b, totals.get(b.id, (Decimal("0"), 0, 0, 0)))
            for b in batches
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{batch_id}", response_model=PayoutBatchDetail)
def get_payout_run(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        batch = payout_service.get_batch(db, batch_id)
    except PayoutNotFound as exc:
        raise _translate(exc)

    items = payout_service.list_items(db, batch.id)
    totals = payout_service.batch_totals(db, [batch.id]).get(
        batch.id, (Decimal("0"), 0, 0, 0)
    )
    return PayoutBatchDetail(
        **_serialize_batch(batch, totals).model_dump(),
        items=_serialize_items(db, items),
    )


@router.post("/{batch_id}/approve", response_model=PayoutBatchDetail)
def approve_payout_run(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        batch = payout_service.approve_batch(db, batch_id, actor)
    except (PayoutNotFound, InvalidBatchState) as exc:
        raise _translate(exc)

    items = payout_service.list_items(db, batch.id)
    totals = payout_service.batch_totals(db, [batch.id]).get(
        batch.id, (Decimal("0"), 0, 0, 0)
    )
    return PayoutBatchDetail(
        **_serialize_batch(batch, totals).model_dump(),
        items=_serialize_items(db, items),
    )


@router.post("/{batch_id}/dispatch", response_model=PayoutDispatchResult)
def dispatch_payout_run(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Pay every pending or failed item and report what actually happened.

    Safe to call again: a failed item is retried, an already-paid item replays
    its payment instead of creating a second one.
    """
    try:
        batch, paid, failed, pending = payout_service.dispatch_batch(
            db, batch_id, actor
        )
    except (PayoutNotFound, InvalidBatchState) as exc:
        raise _translate(exc)

    totals = payout_service.batch_totals(db, [batch.id]).get(
        batch.id, (Decimal("0"), 0, 0, 0)
    )
    return PayoutDispatchResult(
        batch=_serialize_batch(batch, totals),
        paid=paid,
        failed=failed,
        pending=pending,
    )


@router.post("/{batch_id}/cancel", response_model=PayoutBatchDetail)
def cancel_payout_run(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        batch = payout_service.cancel_batch(db, batch_id, actor)
    except (PayoutNotFound, InvalidBatchState) as exc:
        raise _translate(exc)

    items = payout_service.list_items(db, batch.id)
    totals = payout_service.batch_totals(db, [batch.id]).get(
        batch.id, (Decimal("0"), 0, 0, 0)
    )
    return PayoutBatchDetail(
        **_serialize_batch(batch, totals).model_dump(),
        items=_serialize_items(db, items),
    )


@router.get("/{batch_id}/rail-file", response_class=Response)
def download_rail_file(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    The file this run's rail expects — M-Pesa B2C bulk upload today.

    Only members without a payment are in the file: a row that already has a
    payment would pay that member twice. No BOM, unlike the Excel-facing
    exports, because a payment portal reads this file.

    409 with a readable reason when the method has no file (cash), when the
    rail needs data the member record does not have (bank accounts), or when
    everyone in the run is already paid.
    """
    try:
        batch = payout_service.get_batch(db, batch_id)
    except PayoutNotFound as exc:
        raise _translate(exc)

    items = payout_service.list_items(db, batch.id)
    rows = [
        rail_service.RailRow(
            farmer_id=item.farmer_id,
            farmer_name=item.farmer_name,
            phone=item.phone,
            amount=item.amount,
            currency=item.currency,
            status=item.status.value,
        )
        for item in _serialize_items(db, items)
    ]

    try:
        rail_file = rail_service.build_file(batch, rows)
    except rail_service.RailError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))

    return Response(
        content=rail_file.content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (f'attachment; filename="{rail_file.filename}"'),
            "Cache-Control": "no-store",
            "X-Payout-Rows": str(rail_file.row_count),
        },
    )


@router.get("/{batch_id}/export", response_class=Response)
def export_payout_run(
    batch_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    The run as a disbursement file: one row per member, destination included.

    This is what an administrator uploads to the bank or the M-Pesa portal, so
    it carries the phone number, not just the name. Failed rows are included
    with their status and error — a file that quietly omits a member is how
    someone gets missed on payday.
    """
    try:
        batch = payout_service.get_batch(db, batch_id)
    except PayoutNotFound as exc:
        raise _translate(exc)

    items = payout_service.list_items(db, batch.id)
    rows = _serialize_items(db, items[:MAX_EXPORT_ROWS])

    handle = batch.reference or batch.id.hex[:8]
    return csv_response(
        filename=f"payout-{handle}-{date.today().isoformat()}.csv",
        header=[
            "reference",
            "farmer_id",
            "farmer",
            "phone",
            "amount",
            "currency",
            "method",
            "status",
            "payment_id",
            "error",
        ],
        rows=[
            (
                batch.reference,
                item.farmer_id,
                item.farmer_name,
                item.phone,
                item.amount,
                item.currency,
                batch.method,
                # The response model holds the enum; the file wants the word.
                item.status.value,
                item.payment_id,
                item.error,
            )
            for item in rows
        ],
    )
