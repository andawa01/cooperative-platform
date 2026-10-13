"""
Farmer endpoints.

Thin layer: parse request → call service → translate exceptions → return.
Business logic lives in the service.

Permissions:
- create, read, list: admin + clerk
- update: admin only
- verify, archive: admin only
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.farmer import FarmerStatus
from app.models.user import User, UserRole
from app.schemas.farmer import (
    FarmerCreate,
    FarmerListResponse,
    FarmerResponse,
    FarmerUpdate,
)
from app.services import farmer as farmer_service
from app.services.farmer import (
    FarmerNationalIdTaken,
    FarmerNotFound,
    FarmerPhoneTaken,
    InvalidPhoneFormat,
)


router = APIRouter(prefix="/farmers", tags=["farmers"])


# ---------------------------------------------------------------------------
# Exception → HTTP mapping
# ---------------------------------------------------------------------------

def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, FarmerNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")
    if isinstance(exc, FarmerPhoneTaken):
        return HTTPException(status.HTTP_409_CONFLICT, "Phone is already registered")
    if isinstance(exc, FarmerNationalIdTaken):
        return HTTPException(status.HTTP_409_CONFLICT, "National ID is already registered")
    if isinstance(exc, InvalidPhoneFormat):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=FarmerResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_farmer(
    payload: FarmerCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """Register a farmer. Admin or clerk."""
    try:
        return farmer_service.create_farmer(db, payload, actor)
    except (FarmerPhoneTaken, FarmerNationalIdTaken, InvalidPhoneFormat) as exc:
        raise _translate(exc)


@router.get("", response_model=FarmerListResponse)
def list_farmers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    status_filter: FarmerStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=100),
    include_merged: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    List farmers with filters and pagination.

    By default, merged farmers are excluded. Pass include_merged=true to
    include them.
    """
    items, total = farmer_service.list_farmers(
        db,
        status=status_filter,
        search=search,
        include_merged=include_merged,
        limit=limit,
        offset=offset,
    )
    return FarmerListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{farmer_id}", response_model=FarmerResponse)
def get_farmer(
    farmer_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return farmer_service.get_farmer(db, farmer_id)
    except FarmerNotFound as exc:
        raise _translate(exc)


@router.patch("/{farmer_id}", response_model=FarmerResponse)
def update_farmer(
    farmer_id: uuid.UUID,
    payload: FarmerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """Partial update. Admin only. Phone and status are not patchable here."""
    try:
        return farmer_service.update_farmer(db, farmer_id, payload)
    except FarmerNotFound as exc:
        raise _translate(exc)
    except FarmerNationalIdTaken as exc:
        raise _translate(exc)


@router.post("/{farmer_id}/verify", response_model=FarmerResponse)
def verify_farmer(
    farmer_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """Mark a farmer as verified. Admin only. Idempotent."""
    try:
        return farmer_service.verify_farmer(db, farmer_id, actor)
    except FarmerNotFound as exc:
        raise _translate(exc)


@router.post("/{farmer_id}/archive", response_model=FarmerResponse)
def archive_farmer(
    farmer_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """Archive a farmer. Admin only. Idempotent. No hard delete exists."""
    try:
        return farmer_service.archive_farmer(db, farmer_id)
    except FarmerNotFound as exc:
        raise _translate(exc)