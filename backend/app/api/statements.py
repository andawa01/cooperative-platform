"""
Statement endpoint.

Reuses ledger math so the closing pair equals /farmers/{id}/balance when
the statement covers through today.
"""
import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.statement import FarmerStatementResponse
from app.services import statement as statement_service
from app.services.farmer import FarmerNotFound
from app.services import farmer as farmer_service


router = APIRouter(tags=["statements"])


@router.get(
    "/farmers/{farmer_id}/statement",
    response_model=FarmerStatementResponse,
)
def get_statement(
    farmer_id: uuid.UUID,
    start: date | None = Query(default=None, description="YYYY-MM-DD"),
    end: date | None = Query(default=None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        farmer_service.get_farmer(db, farmer_id)
    except FarmerNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Farmer not found")

    today = date.today()
    end_date = end or today
    start_date = start or (end_date - __import__("datetime").timedelta(days=365))

    if start_date > end_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "start must be <= end",
        )
    if (end_date - start_date).days > 730:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "range may not exceed 2 years",
        )

    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

    return statement_service.build_statement(db, farmer_id, start_dt, end_dt)