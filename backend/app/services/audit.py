"""
Audit trail service (D-031).

Two rules govern this module:

1. **Record inside the caller's transaction.** `record()` only adds to the
   session — it never commits. The caller's `write_transaction` is what makes
   "the change and its audit row are atomic" true. If the action fails and
   rolls back, its audit row disappears with it, which is exactly right:
   the log must not contain actions that did not happen.

2. **Say what changed, not everything that exists.** `before`/`after` are
   small dicts of the fields a human would ask about (amount, rate, status,
   reason). Dumping whole rows would put PII in the trail and make it
   unreadable.

The request id is read from the request context automatically, so an entry
links back to the log line of the request that produced it.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_request_id
from app.models.audit import AuditLog
from app.models.user import User


def snapshot(value: Any) -> Any:
    """
    JSON-safe representation of a value for a before/after payload.

    Dates, UUIDs and Decimals become strings (the same convention the API
    uses for money — decimals are strings, never floats). Anything else is
    passed through; callers only put simple fields in payloads.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def record(
    db: Session,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """
    Append one audit entry to the session. Does NOT commit.

    Must be called inside the transaction that performs the change it
    describes. Returning the (unflushed) entry lets a caller include it in
    a later flush without a second query.
    """
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        request_id=request_id if request_id is not None else get_request_id(),
    )
    db.add(entry)
    return entry


def list_entries(
    db: Session,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[tuple[AuditLog, str | None]], int]:
    """
    List audit entries newest-first with the actor's name resolved.

    Returns ([(entry, actor_name), ...], total). The name is joined in the
    same query — a list screen must not cost one query per row (D-027).
    `actor_name` is None for system actions and for actors that no longer
    exist.
    """
    stmt = select(AuditLog, User.full_name).join(
        User, User.id == AuditLog.actor_id, isouter=True
    )
    count_stmt = select(func.count()).select_from(AuditLog)

    conditions = []
    if action is not None:
        conditions.append(AuditLog.action == action)
    if entity_type is not None:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_id is not None:
        conditions.append(AuditLog.actor_id == actor_id)

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    stmt = (
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = db.execute(stmt).all()
    total = db.scalar(count_stmt) or 0
    return [(row[0], row[1]) for row in rows], total
