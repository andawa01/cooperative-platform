"""
Reporting endpoints.

One report so far: production by collection point (D-039). It is the question
management actually asks — "how much came in at Kisumu Central this month?" —
and the reason collection points had to become a table rather than a string.
"""

from datetime import UTC, date, datetime, time

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.collection_point import CollectionPoint
from app.models.delivery import Delivery
from app.models.user import User
from app.schemas.collection_point import ProductionByPointResponse, ProductionByPointRow

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/production-by-point", response_model=ProductionByPointResponse)
def production_by_point(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    delivered_from: date | None = Query(default=None),
    delivered_to: date | None = Query(default=None),
):
    """
    Net quantity and value per collection point.

    Reversals are included with their negative quantity, so this is what the
    co-op actually kept, not what was first written down. Deliveries with no
    point appear under "Unassigned" rather than being dropped — a report that
    hides a fifth of the intake is worse than one that shows a gap.
    """
    conditions = []
    if delivered_from is not None:
        conditions.append(
            Delivery.delivered_at
            >= datetime.combine(delivered_from, time.min, tzinfo=UTC)
        )
    if delivered_to is not None:
        conditions.append(
            Delivery.delivered_at < datetime.combine(delivered_to, time.min, tzinfo=UTC)
        )

    stmt = (
        select(
            Delivery.collection_point_id,
            CollectionPoint.name,
            CollectionPoint.code,
            func.count(Delivery.id),
            func.coalesce(func.sum(Delivery.quantity), 0),
            func.coalesce(func.sum(Delivery.quantity * Delivery.rate_snapshot), 0),
        )
        .join(
            CollectionPoint,
            CollectionPoint.id == Delivery.collection_point_id,
            isouter=True,
        )
        .group_by(
            Delivery.collection_point_id,
            CollectionPoint.name,
            CollectionPoint.code,
        )
        .order_by(func.coalesce(func.sum(Delivery.quantity), 0).desc())
    )
    for condition in conditions:
        stmt = stmt.where(condition)

    rows = db.execute(stmt).all()
    return ProductionByPointResponse(
        delivered_from=delivered_from.isoformat() if delivered_from else None,
        delivered_to=delivered_to.isoformat() if delivered_to else None,
        items=[
            ProductionByPointRow(
                collection_point_id=point_id,
                collection_point_name=name or "Unassigned",
                collection_point_code=code,
                entries=int(entries),
                quantity=quantity,
                value=value,
                currency=settings.default_currency,
            )
            for point_id, name, code, entries, quantity, value in rows
        ],
    )
