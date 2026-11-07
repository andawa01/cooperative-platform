"""
Collection point service (D-039).

Small on purpose: points are reference data. The rules worth enforcing are
uniqueness (a duplicated code makes every report ambiguous), a canonical code
form (staff type lower case; reports and files should not have to care), and
"you cannot assign a member to a retired point" — that is how a delivery ends
up somewhere nobody is collecting.
"""

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import write_transaction
from app.models.collection_point import CollectionPoint
from app.models.user import User
from app.schemas.collection_point import CollectionPointCreate, CollectionPointUpdate
from app.services import audit

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class CollectionPointNotFound(Exception):
    pass


class CollectionPointInactive(Exception):
    pass


class CollectionPointCodeTaken(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical_code(code: str) -> str:
    return code.strip().upper()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def resolve_active_point(db: Session, point_id: uuid.UUID) -> CollectionPoint:
    """
    Load a point that may receive new members or deliveries.

    A retired point stays readable for history, but nothing new is assigned
    to it — the failure is loud rather than a silently wrong report.
    """
    point = db.get(CollectionPoint, point_id)
    if point is None:
        raise CollectionPointNotFound()
    if not point.is_active:
        raise CollectionPointInactive(
            f"collection point {point.code} is inactive and cannot take new records"
        )
    return point


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def create_point(
    db: Session, data: CollectionPointCreate, actor: User
) -> CollectionPoint:
    with write_transaction(db):
        point = CollectionPoint(
            name=data.name.strip(),
            code=_canonical_code(data.code),
            county=_clean(data.county),
            ward=_clean(data.ward),
            zone=_clean(data.zone),
            scale_id=_clean(data.scale_id),
            is_active=True,
            created_by_id=actor.id,
        )
        db.add(point)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if "uq_collection_point_code" in str(exc.orig).lower():
                raise CollectionPointCodeTaken() from exc
            raise

        audit.record(
            db,
            actor_id=actor.id,
            action="collection_point.create",
            entity_type="collection_point",
            entity_id=point.id,
            after={
                "name": point.name,
                "code": point.code,
                "county": point.county,
                "ward": point.ward,
                "zone": point.zone,
            },
        )
        db.flush()
        db.refresh(point)

    return point


def update_point(
    db: Session,
    point_id: uuid.UUID,
    data: CollectionPointUpdate,
    actor: User,
) -> CollectionPoint:
    """PATCH semantics; writes an audit entry only if something changed."""
    with write_transaction(db):
        point = db.get(CollectionPoint, point_id)
        if point is None:
            raise CollectionPointNotFound()

        updates = data.model_dump(exclude_unset=True)
        before: dict = {}
        after: dict = {}

        for key, value in updates.items():
            if key == "code" and value is not None:
                value = _canonical_code(value)
            elif key in {"name", "county", "ward", "zone", "scale_id"}:
                value = _clean(value) if key != "name" else value.strip()
            previous = getattr(point, key)
            if previous == value:
                continue
            before[key] = audit.snapshot(previous)
            after[key] = audit.snapshot(value)
            setattr(point, key, value)

        if not before:
            return point

        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if "uq_collection_point_code" in str(exc.orig).lower():
                raise CollectionPointCodeTaken() from exc
            raise

        audit.record(
            db,
            actor_id=actor.id,
            action="collection_point.update",
            entity_type="collection_point",
            entity_id=point.id,
            before=before,
            after=after,
        )
        db.flush()
        db.refresh(point)

    return point


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def get_point(db: Session, point_id: uuid.UUID) -> CollectionPoint:
    point = db.get(CollectionPoint, point_id)
    if point is None:
        raise CollectionPointNotFound()
    return point


def list_points(
    db: Session,
    *,
    active_only: bool = False,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[CollectionPoint], int]:
    stmt = select(CollectionPoint)
    count_stmt = select(func.count()).select_from(CollectionPoint)

    conditions = []
    if active_only:
        conditions.append(CollectionPoint.is_active.is_(True))
    if search:
        pattern = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(CollectionPoint.name).like(pattern),
                func.lower(CollectionPoint.code).like(pattern),
                func.lower(CollectionPoint.county).like(pattern),
            )
        )

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    stmt = stmt.order_by(CollectionPoint.name.asc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all()), db.scalar(count_stmt) or 0
