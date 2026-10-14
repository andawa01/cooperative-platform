"""
Produce line and rate endpoints.

Permissions:
- read (lines, rates): admin + clerk
- write (create/update/deactivate lines, create rates): admin only
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.produce import (
    CurrentRateResponse,
    ProduceLineCreate,
    ProduceLineListResponse,
    ProduceLineResponse,
    ProduceLineUpdate,
    RateCreate,
    RateCreateResponse,
    RateResponse,
)
from app.services import produce as produce_service
from app.services.produce import (
    ProduceLineCodeTaken,
    ProduceLineInactive,
    ProduceLineNotFound,
    RateBackdatedBeforePrevious,
    RateOverlap,
)


router = APIRouter(tags=["produce"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, ProduceLineNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Produce line not found")
    if isinstance(exc, ProduceLineCodeTaken):
        return HTTPException(status.HTTP_409_CONFLICT, "Produce line code already exists")
    if isinstance(exc, ProduceLineInactive):
        return HTTPException(status.HTTP_409_CONFLICT, "Produce line is inactive")
    if isinstance(exc, RateBackdatedBeforePrevious):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, RateOverlap):
        return HTTPException(status.HTTP_409_CONFLICT, "Rate overlaps existing interval")
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


# ---------------------------------------------------------------------------
# Produce lines
# ---------------------------------------------------------------------------

@router.post(
    "/produce-lines",
    response_model=ProduceLineResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_produce_line(
    payload: ProduceLineCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        return produce_service.create_produce_line(db, payload, actor)
    except ProduceLineCodeTaken as exc:
        raise _translate(exc)


@router.get("/produce-lines", response_model=ProduceLineListResponse)
def list_produce_lines(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = produce_service.list_produce_lines(
        db, include_inactive=include_inactive, limit=limit, offset=offset
    )
    return ProduceLineListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/produce-lines/{line_id}", response_model=ProduceLineResponse)
def get_produce_line(
    line_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return produce_service.get_produce_line(db, line_id)
    except ProduceLineNotFound as exc:
        raise _translate(exc)


@router.patch("/produce-lines/{line_id}", response_model=ProduceLineResponse)
def update_produce_line(
    line_id: uuid.UUID,
    payload: ProduceLineUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        return produce_service.update_produce_line(db, line_id, payload)
    except ProduceLineNotFound as exc:
        raise _translate(exc)


@router.post(
    "/produce-lines/{line_id}/deactivate",
    response_model=ProduceLineResponse,
)
def deactivate_produce_line(
    line_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        return produce_service.deactivate_produce_line(db, line_id)
    except ProduceLineNotFound as exc:
        raise _translate(exc)


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------

@router.post(
    "/produce-lines/{line_id}/rates",
    response_model=RateCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rate(
    line_id: uuid.UUID,
    payload: RateCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Set a new rate. Closes the current open rate (if any) and inserts the new
    one in a single transaction. Returns both the new rate and the closed
    previous rate, plus a count of affected deliveries (informational only).
    """
    try:
        new_rate, previous, affected = produce_service.create_rate(
            db, line_id, payload, actor
        )
    except (
        ProduceLineNotFound,
        ProduceLineInactive,
        RateBackdatedBeforePrevious,
        RateOverlap,
    ) as exc:
        raise _translate(exc)

    return RateCreateResponse(
        new_rate=RateResponse.model_validate(new_rate),
        previous_rate=RateResponse.model_validate(previous) if previous else None,
        affected_deliveries=affected,
    )


@router.get("/produce-lines/{line_id}/rates", response_model=list[RateResponse])
def list_rates(
    line_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return produce_service.list_rates(db, line_id)
    except ProduceLineNotFound as exc:
        raise _translate(exc)


@router.get(
    "/produce-lines/{line_id}/rates/current",
    response_model=CurrentRateResponse,
)
def get_current_rate(
    line_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Rate effective today. 200 { "rate": null } if none exists for today.
    404 if the produce line itself doesn't exist.
    """
    try:
        rate = produce_service.get_rate_at(db, line_id, date.today())
    except ProduceLineNotFound as exc:
        raise _translate(exc)
    return CurrentRateResponse(
        rate=RateResponse.model_validate(rate) if rate else None
    )


@router.get(
    "/produce-lines/{line_id}/rates/at",
    response_model=CurrentRateResponse,
)
def get_rate_at_date(
    line_id: uuid.UUID,
    on: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Rate effective on a specific date. Used by reporting and corrections."""
    try:
        rate = produce_service.get_rate_at(db, line_id, on)
    except ProduceLineNotFound as exc:
        raise _translate(exc)
    return CurrentRateResponse(
        rate=RateResponse.model_validate(rate) if rate else None
    )