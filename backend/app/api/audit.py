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
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.csv import MAX_EXPORT_ROWS, csv_response
from app.api.deps import require_role
from app.db.session import get_db
from app.models.audit import AUDIT_ACTIONS, AUDIT_ENTITY_TYPES, AuditLog
from app.models.deduction import Deduction
from app.models.delivery import Delivery
from app.models.farmer import Farmer
from app.models.payment import Payment
from app.models.produce import ProduceLine, Rate
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


def _amount(value: Decimal) -> str:
    """`250.0000` reads as `250` — trailing zeros are noise in a label."""
    return f"{value.normalize():f}"


def _entity_labels(db: Session, entries: list[AuditLog]) -> dict[uuid.UUID, str]:
    """
        Human names for the entities on this page, in one query per entity type.

        An audit row stores an id, and an id means nothing to a manager reading the
    trail — `e0ef997f` could be any of the co-op's rates. The label is derived on
        read rather than stored, so renaming a farmer or a produce line does not
        require rewriting history (and would be forbidden anyway: the trail is
        append-only).

        Batched by type: a page of 50 mixed rows costs at most six queries, not
        fifty (D-027). Types we cannot name, or rows that have since been deleted,
        are simply absent from the map and the client falls back to the short id.
    """
    by_type: dict[str, set[uuid.UUID]] = {}
    for entry in entries:
        by_type.setdefault(entry.entity_type, set()).add(entry.entity_id)

    labels: dict[uuid.UUID, str] = {}

    delivery_ids = by_type.get("delivery")
    if delivery_ids:
        rows = db.execute(
            select(Delivery.id, Farmer.first_name, Farmer.last_name, ProduceLine.name)
            .join(Farmer, Farmer.id == Delivery.farmer_id)
            .join(ProduceLine, ProduceLine.id == Delivery.produce_line_id)
            .where(Delivery.id.in_(delivery_ids))
        ).all()
        for entity_id, first, last, line_name in rows:
            labels[entity_id] = f"{first} {last} — {line_name}"

    payment_ids = by_type.get("payment")
    if payment_ids:
        rows = db.execute(
            select(
                Payment.id,
                Farmer.first_name,
                Farmer.last_name,
                Payment.amount,
                Payment.currency,
            )
            .join(Farmer, Farmer.id == Payment.farmer_id)
            .where(Payment.id.in_(payment_ids))
        ).all()
        for entity_id, first, last, amount, currency in rows:
            labels[entity_id] = f"{first} {last} — {_amount(amount)} {currency}"

    deduction_ids = by_type.get("deduction")
    if deduction_ids:
        rows = db.execute(
            select(
                Deduction.id,
                Farmer.first_name,
                Farmer.last_name,
                Deduction.amount,
                Deduction.currency,
                Deduction.reason_code,
            )
            .join(Farmer, Farmer.id == Deduction.farmer_id)
            .where(Deduction.id.in_(deduction_ids))
        ).all()
        for entity_id, first, last, amount, currency, reason in rows:
            labels[entity_id] = (
                f"{first} {last} — {_amount(amount)} {currency} "
                f"{reason.replace('_', ' ')}"
            )

    rate_ids = by_type.get("rate")
    if rate_ids:
        rows = db.execute(
            select(
                Rate.id,
                ProduceLine.name,
                ProduceLine.unit,
                Rate.rate_per_unit,
                Rate.currency,
            )
            .join(ProduceLine, ProduceLine.id == Rate.produce_line_id)
            .where(Rate.id.in_(rate_ids))
        ).all()
        for entity_id, line_name, unit, amount, currency in rows:
            labels[entity_id] = f"{line_name} — {_amount(amount)} {currency}/{unit}"

    farmer_ids = by_type.get("farmer")
    if farmer_ids:
        for farmer in db.scalars(select(Farmer).where(Farmer.id.in_(farmer_ids))):
            labels[farmer.id] = farmer.full_name

    user_ids = by_type.get("user")
    if user_ids:
        for user in db.scalars(select(User).where(User.id.in_(user_ids))):
            labels[user.id] = f"{user.full_name} ({user.email})"

    return labels


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
    labels = _entity_labels(db, [entry for entry, _actor in rows])
    items = [
        AuditEntryResponse(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            entity_label=labels.get(entry.entity_id),
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


@router.get("/export", response_class=Response)
def export_audit(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
    action: str | None = Query(default=None, max_length=64),
    entity_type: str | None = Query(default=None, max_length=32),
    entity_id: uuid.UUID | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
):
    """
    The filtered audit trail as CSV, for an external auditor.

    `before`/`after` are flattened to compact JSON in a single column: an
    auditor needs the evidence intact, not a paraphrase of it.
    """
    import json

    _validated(action, AUDIT_ACTIONS, "action")
    _validated(entity_type, AUDIT_ENTITY_TYPES, "entity_type")

    rows, _total = audit_service.list_entries(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        limit=MAX_EXPORT_ROWS,
        offset=0,
    )

    def _json(value: dict | None) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":")) if value else ""

    labels = _entity_labels(db, [entry for entry, _actor in rows])

    return csv_response(
        filename=f"audit-{date.today().isoformat()}.csv",
        header=[
            "created_at",
            "action",
            "entity_type",
            "entity_label",
            "entity_id",
            "actor",
            "actor_id",
            "before",
            "after",
            "request_id",
        ],
        rows=[
            (
                entry.created_at,
                entry.action,
                entry.entity_type,
                labels.get(entry.entity_id),
                entry.entity_id,
                actor_name or "system",
                entry.actor_id,
                _json(entry.before),
                _json(entry.after),
                entry.request_id,
            )
            for entry, actor_name in rows
        ],
    )
