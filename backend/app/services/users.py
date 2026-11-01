"""
User administration.

This module owns "who may act, and what may they do". Two rules live here
that the database cannot express, and both exist to stop an administrator
locking everyone out of the system:

- **You cannot change your own role, or deactivate your own account.** With
  a single admin that turns the system into one nobody can administer.
- **The last active admin cannot be demoted or deactivated.** Same failure,
  one step removed: the actor is a different admin, but the outcome is still
  a co-op with no administrator.

Deactivation bumps `token_version`, exactly like a password change (D-030).
The point of deactivating an account is that its session stops working *now*,
not whenever the token happens to expire.
"""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import write_transaction
from app.models.user import User, UserRole
from app.schemas.user import UserUpdateRequest
from app.services import audit


class UserNotFound(Exception):
    """No account with that id."""


class SelfModification(Exception):
    """The actor tried to change their own role or deactivate themselves."""


class LastAdmin(Exception):
    """The change would leave the system with no active administrator."""


def list_users(
    db: Session,
    *,
    search: str | None = None,
    role: UserRole | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[User], int]:
    """
    List accounts, newest first, with an optional search over name and email.

    Returns (items, total) where total is the count before limit/offset, so
    the client can render pagination without a second request.
    """
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    conditions = []

    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        conditions.append(
            func.lower(User.email).like(pattern)
            | func.lower(User.full_name).like(pattern)
        )
    if role is not None:
        conditions.append(User.role == role.value)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    stmt = (
        stmt.order_by(User.created_at.asc(), User.id.asc())
        .limit(limit)
        .offset(offset)
    )

    items = list(db.scalars(stmt).all())
    total = db.scalar(count_stmt) or 0
    return items, total


def update_user(
    db: Session,
    user_id: uuid.UUID,
    payload: UserUpdateRequest,
    actor: User,
) -> User:
    """
    Apply a partial update, refusing anything that could lock the system out.

    Only genuine changes are written and audited, so re-sending the same
    values is a no-op that leaves no trail entry.
    """
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFound()

    # Collect (old, new) pairs for the fields that actually differ.
    changes: dict[str, tuple[Any, Any]] = {}

    if payload.full_name is not None:
        cleaned = payload.full_name.strip()
        if cleaned != user.full_name:
            changes["full_name"] = (user.full_name, cleaned)

    if payload.role is not None and payload.role.value != user.role:
        changes["role"] = (user.role, payload.role.value)

    if payload.is_active is not None and payload.is_active != user.is_active:
        changes["is_active"] = (user.is_active, payload.is_active)

    if not changes:
        return user

    if user.id == actor.id:
        if "role" in changes:
            raise SelfModification("You cannot change your own role")
        if "is_active" in changes:
            raise SelfModification("You cannot deactivate your own account")

    # Would this change remove the final active admin?
    new_role = changes["role"][1] if "role" in changes else user.role
    new_active = changes["is_active"][1] if "is_active" in changes else user.is_active
    was_admin = user.role == UserRole.ADMIN.value and user.is_active
    stays_admin = new_role == UserRole.ADMIN.value and new_active

    if was_admin and not stays_admin:
        other_admins = (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == UserRole.ADMIN.value,
                    User.is_active.is_(True),
                    User.id != user.id,
                )
            )
            or 0
        )
        if other_admins == 0:
            raise LastAdmin()

    with write_transaction(db):
        before: dict[str, Any] = {}
        after: dict[str, Any] = {}

        for field, (old, new) in changes.items():
            before[field] = old
            after[field] = new
            setattr(user, field, new)

        if "is_active" in changes and changes["is_active"][1] is False:
            # Kill every live session for this account immediately.
            user.token_version = (user.token_version or 0) + 1
            after["sessions_invalidated"] = True

        audit.record(
            db,
            actor_id=actor.id,
            action="user.update",
            entity_type="user",
            entity_id=user.id,
            before=before,
            after=after,
        )

    db.refresh(user)
    return user
