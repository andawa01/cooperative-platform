"""
Collection point endpoints (D-039).

Permissions mirror the other reference data (produce lines):
- read: admin + clerk. A clerk registering a member must pick a point.
- write: admin only. A duplicate or retired point corrupts reporting, which
  is a supervisory decision, not a counter one.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.collection_point import (
    CollectionPointCreate,
    CollectionPointListResponse,
    CollectionPointResponse,
    CollectionPointUpdate,
)
from app.services import collection_point as point_service
from app.services.collection_point import (
    CollectionPointCodeTaken,
    CollectionPointInactive,
    CollectionPointNotFound,
)

router = APIRouter(prefix="/collection-points", tags=["collection-points"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, CollectionPointNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Collection point not found")
    if isinstance(exc, CollectionPointCodeTaken):
        return HTTPException(
            status.HTTP_409_CONFLICT, "That collection point code already exists"
        )
    if isinstance(exc, CollectionPointInactive):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


@router.post(
    "", response_model=CollectionPointResponse, status_code=status.HTTP_201_CREATED
)
def create_collection_point(
    payload: CollectionPointCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        return point_service.create_point(db, payload, actor)
    except (CollectionPointCodeTaken, CollectionPointInactive) as exc:
        raise _translate(exc)


@router.get("", response_model=CollectionPointListResponse)
def list_collection_points(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    active_only: bool = Query(default=False),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = point_service.list_points(
        db,
        active_only=active_only,
        search=search,
        limit=limit,
        offset=offset,
    )
    return CollectionPointListResponse(
        items=items, total=total, limit=limit, offset=offset
    )


@router.get("/{point_id}", response_model=CollectionPointResponse)
def get_collection_point(
    point_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        return point_service.get_point(db, point_id)
    except CollectionPointNotFound as exc:
        raise _translate(exc)


@router.patch("/{point_id}", response_model=CollectionPointResponse)
def update_collection_point(
    point_id: uuid.UUID,
    payload: CollectionPointUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """Rename, re-code or retire a point. `is_active: false` retires it."""
    try:
        return point_service.update_point(db, point_id, payload, actor)
    except (
        CollectionPointNotFound,
        CollectionPointCodeTaken,
        CollectionPointInactive,
    ) as exc:
        raise _translate(exc)
