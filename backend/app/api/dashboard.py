"""
Dashboard endpoint.

Returns cooperative-wide summary statistics in a single request so the
frontend does not have to fire a dozen queries just to render the home
screen. Every figure is derived by the dashboard service from the same
ledger formulas as balance and statement, so the numbers cannot disagree
(see app/services/dashboard.py).

Permissions: admin + clerk. The dashboard is the home screen for both roles;
it exposes no field a clerk cannot already read elsewhere.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import DashboardSummary
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(
    days: int = Query(
        default=30,
        ge=1,
        le=730,
        description="Lookback window in days, including today.",
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Dashboard summary for the last `days` days.

    - `farmers_total` / `farmers_by_status`: lifecycle breakdown, all time.
    - `*_in_period`: activity dated by the business event (delivered_at,
      paid_at), not by when the clerk entered it.
    - `outstanding_debt_total` / `available_credit_total`: cooperative-wide
      ledger position, all time, equal to the sum of every farmer's balance.
    - `deliveries_by_line` / `deliveries_daily`: chart series; daily buckets
      are zero-filled across the whole period.
    - `recent_activity`: the newest deliveries, reversals and payments.
    """
    return dashboard_service.build_dashboard_summary(db, period_days=days)
