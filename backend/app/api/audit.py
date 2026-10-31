"""
Audit endpoints — read access to the append-only trail (D-031).

Admin only, deliberately: the trail records who did what to every farmer's
money, and also who logged in, changed passwords, and created accounts.
Clerks have no legitimate need for it, and an audit trail readable by
everyone is a reconnaissance tool for whoever gets a clerk token.

There is no POST, PATCH or DELETE here. The table's trigger enforces the
same thing; this router simply not offering a write path keeps the intent
obvious.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.session import get_db
from app.models.audit import AUDIT_ACTIONS, AUDIT_ENTITY_TYPES
from app.models.user import User, UserRole
from app.schemas.audit import AuditEntryResponse, AuditListResponse
from app.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


def _validated(value: str | None, allowed: tuple[str, ...], field: str) -> str | None:
    """
    Reject unknown filter values with 422.

    An unrecognised action means a typo, a stale client, or an action
    nobody wired up — all worth failing loudly on rather than returning an
    empty page that looks like "nothing happened".
    """
    if value is not None and value not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Unknown {field}: {value!r}",
        )
    return value


@router.get("", response_model=AuditListResponse)
def list_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
    action: str | None = Query(default=None, max_length=64),
    entity_type: str | None = Query(default=None, max_length=32),
    entity_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    List audit entries, newest first.

    Filters compose: `entity_type` + `entity_id` answers "what happened to
    this row" (the question a farmer's dispute actually asks), `action`
    answers "every payment reversal this month", `actor_id` answers "what
    has this account touched".
    """
    _validated(action, AUDIT_ACTIONS, "action")
    _validated(entity_type, AUDIT_ENTITY_TYPES, "entity_type")

    rows, total = audit_service.list_entries(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    items = [
        AuditEntryResponse(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            actor_id=entry.actor_id,
            actor_name=actor_name,
            before=entry.before,
            after=entry.after,
            request_id=entry.request_id,
            created_at=entry.created_at,
        )
        for entry, actor_name in rows
    ]
    return AuditListResponse(items=items, total=total, limit=limit, offset=offset)
