"""
User administration endpoints.

Admin only, for the same reason the audit trail is: this is the list of
accounts that can move money. Creating an account is still
`POST /auth/register` (already admin-guarded once any user exists) — this
router adds the listing and the role/active lifecycle that were previously
only settable at registration.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import UserResponse
from app.schemas.user import UserListResponse, UserUpdateRequest
from app.services import users as users_service
from app.services.users import LastAdmin, SelfModification, UserNotFound

router = APIRouter(prefix="/users", tags=["users"])


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, UserNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if isinstance(exc, SelfModification):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, LastAdmin):
        return HTTPException(
            status.HTTP_409_CONFLICT,
            "At least one active administrator must remain",
        )
    return HTTPException(status.HTTP_400_BAD_REQUEST, "Bad request")


@router.get("", response_model=UserListResponse)
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
    search: str | None = Query(default=None, max_length=255),
    role: UserRole | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List accounts, optionally filtered by a name/email search or role."""
    items, total = users_service.list_users(
        db, search=search, role=role, limit=limit, offset=offset
    )
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Change a user's name, role, or active state.

    Deactivating bumps `token_version`, so the account's existing tokens stop
    working immediately rather than at their natural expiry.
    """
    try:
        return users_service.update_user(db, user_id, payload, actor)
    except (UserNotFound, SelfModification, LastAdmin) as exc:
        raise _translate(exc)
