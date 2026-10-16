"""
Notification endpoints.

Permissions (see D-015):
- read: admin + clerk
- retry: admin only

The response merges the durable record (Postgres) with the current dispatch
state (Redis) into one coherent object.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
)
from app.services import notifications as notif_service
from app.services.notifications import NotificationNotFound


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(db: Session, n) -> NotificationResponse:
    """
    Merge the Postgres row with the Redis dispatch state.
    """
    state = notif_service.get_dispatch_state(n.id)
    return NotificationResponse(
        id=n.id,
        farmer_id=n.farmer_id,
        channel=n.channel,
        template=n.template,
        recipient=n.recipient,
        content=n.content,
        related_entity_type=n.related_entity_type,
        related_entity_id=n.related_entity_id,
        created_at=n.created_at,
        status=state["status"],
        attempts=state["attempts"],
        last_error=state["last_error"],
        sent_at=state["sent_at"],
    )


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    farmer_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, total = notif_service.list_notifications(
        db, farmer_id=farmer_id, limit=limit, offset=offset
    )
    return NotificationListResponse(
        items=[_serialize(db, n) for n in items],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{notification_id}", response_model=NotificationResponse)
def get_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        n = notif_service.get_notification(db, notification_id)
    except NotificationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return _serialize(db, n)


@router.post(
    "/{notification_id}/retry",
    response_model=NotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_notification(
    notification_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """
    Re-enqueue a notification. Admin only.

    Useful when:
    - A notification failed permanently and needs another attempt.
    - Redis was unreachable at enqueue time; the record exists but the job
      never reached the queue.
    """
    try:
        n = notif_service.retry_notification(db, notification_id)
    except NotificationNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notification not found")
    return _serialize(db, n)