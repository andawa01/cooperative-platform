"""
Dashboard aggregation service.

One request answers what a cooperative manager opens the app to ask: how did
this period go, where do we stand financially in total, and what just
happened?

Consistency is the point of this module. The global financial totals use the
*same* formulas as `app/services/ledger.py`, so that:

    sum(compute_balance(f).outstanding_debt for f in farmers)
        == dashboard.outstanding_debt_total

and likewise for available credit and the pending-valuation count. The
dashboard does not re-invent the ledger; it aggregates it cooperatively. If
the two ever disagree, one of them is buggy — `test_dashboard.py` asserts the
invariant directly.

Period conventions:
- "last N days" means today plus the N-1 days before it, in UTC. So
  `days=30` covers exactly 30 calendar days and yields exactly 30 daily
  buckets, including days with no activity.
- Period activity is dated by the business event (`delivered_at`,
  `paid_at`), not by `recorded_at` — same rule as the statement (D-021).

Read-only: no locks, no transaction of its own. Aggregates over a
cooperative-sized dataset are cheap at MVP scale; if that stops being true,
the same response shape can be served from materialised views (D-010).
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.deduction import Deduction
from app.models.delivery import Delivery
from app.models.farmer import Farmer, FarmerStatus
from app.models.payment import Payment, PaymentAllocation
from app.models.produce import ProduceLine
from app.schemas.dashboard import (
    ActivityItem,
    DashboardSummary,
    DeliveriesByLine,
    DeliveriesDaily,
    FarmersByStatus,
)
from app.services.statement import (
    describe_deduction,
    describe_delivery,
    describe_payment,
)

ZERO = Decimal("0.0000")

# How many recent events the activity feed carries. The dashboard shows a
# short "what just happened" list, not a paginated audit log.
ACTIVITY_LIMIT = 10


def _period_bounds(period_days: int) -> tuple[date, datetime]:
    """
    Return (first_calendar_day, first_instant) for the period.

    Half-open in spirit: everything at or after `first_instant` belongs to
    the period, and there is no upper bound — the DB rejects future-dated
    deliveries and payments beyond a 1-hour clock-skew tolerance.
    """
    today = datetime.now(UTC).date()
    first_day = today - timedelta(days=period_days - 1)
    first_instant = datetime.combine(first_day, time.min, tzinfo=UTC)
    return first_day, first_instant


# ---------------------------------------------------------------------------
# Farmers
# ---------------------------------------------------------------------------


def _farmers(db: Session) -> tuple[int, FarmersByStatus]:
    total = db.scalar(select(func.count()).select_from(Farmer)) or 0

    rows = db.execute(
        select(Farmer.status, func.count()).select_from(Farmer).group_by(Farmer.status)
    ).all()
    counts = {status: count for status, count in rows}

    return total, FarmersByStatus(
        pending_verification=counts.get(FarmerStatus.PENDING_VERIFICATION.value, 0),
        active=counts.get(FarmerStatus.ACTIVE.value, 0),
        suspended=counts.get(FarmerStatus.SUSPENDED.value, 0),
        archived=counts.get(FarmerStatus.ARCHIVED.value, 0),
        merged=counts.get(FarmerStatus.MERGED.value, 0),
    )


# ---------------------------------------------------------------------------
# Financial position (global, all time)
# ---------------------------------------------------------------------------


def _financial_position(
    db: Session,
) -> tuple[Decimal, Decimal, Decimal, int]:
    """
    Cooperative-wide counterpart of `ledger.compute_balance`.

    Deliberately mirrors the ledger's sums exactly:

    - Value sums every row with a non-NULL `rate_snapshot`, reversals
      included. Do NOT add `WHERE reversal_of_id IS NULL` anywhere here:
      reversal rows are signed, and the sign is what does the work.
    - Allocations sum every allocation row, reversals included.
    - Pending valuation counts every delivery with a NULL rate, reversals
      included, so the global count equals the sum of per-farmer counts.
    """
    total_delivery_value = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO
                )
            )
            .select_from(Delivery)
            .where(Delivery.rate_snapshot.is_not(None))
        )
        or ZERO
    )

    net_allocations = (
        db.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), ZERO)).select_from(
                PaymentAllocation
            )
        )
        or ZERO
    )

    net_payments = (
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), ZERO)).select_from(Payment)
        )
        or ZERO
    )

    # Withheld from members, reversals included (negative rows net out).
    net_deductions = (
        db.scalar(
            select(func.coalesce(func.sum(Deduction.amount), ZERO)).select_from(
                Deduction
            )
        )
        or ZERO
    )

    outstanding_debt = total_delivery_value - net_allocations
    available_credit = net_payments - net_allocations

    pending_valuation = (
        db.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.rate_snapshot.is_(None))
        )
        or 0
    )

    return outstanding_debt, available_credit, net_deductions, pending_valuation


# ---------------------------------------------------------------------------
# Period activity
# ---------------------------------------------------------------------------


def _period_totals(
    db: Session, first_instant: datetime
) -> tuple[int, Decimal, int, Decimal, int, Decimal]:
    """
    (deliveries_in_period, deliveries_value_in_period,
     payments_in_period, payments_value_in_period)

    Counts are delivery/payment *events* (reversals excluded — a reversal is
    a correction, not a head of produce). Values are net, so a reversed
    delivery or payment drops out of the period's money.
    """
    deliveries_count = (
        db.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.delivered_at >= first_instant)
            .where(Delivery.reversal_of_id.is_(None))
        )
        or 0
    )

    deliveries_value = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO
                )
            )
            .select_from(Delivery)
            .where(Delivery.delivered_at >= first_instant)
        )
        or ZERO
    )

    payments_count = (
        db.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.paid_at >= first_instant)
            .where(Payment.reversal_of_id.is_(None))
        )
        or 0
    )

    payments_value = (
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), ZERO))
            .select_from(Payment)
            .where(Payment.paid_at >= first_instant)
        )
        or ZERO
    )

    deductions_count = (
        db.scalar(
            select(func.count())
            .select_from(Deduction)
            .where(Deduction.applied_at >= first_instant)
            .where(Deduction.reversal_of_id.is_(None))
        )
        or 0
    )

    deductions_value = (
        db.scalar(
            select(func.coalesce(func.sum(Deduction.amount), ZERO))
            .select_from(Deduction)
            .where(Deduction.applied_at >= first_instant)
        )
        or ZERO
    )

    return (
        deliveries_count,
        deliveries_value,
        payments_count,
        payments_value,
        deductions_count,
        deductions_value,
    )


def _deliveries_by_line(db: Session, first_instant: datetime) -> list[DeliveriesByLine]:
    rows = db.execute(
        select(
            ProduceLine.id,
            ProduceLine.name,
            ProduceLine.unit,
            func.count(Delivery.id)
            .filter(Delivery.reversal_of_id.is_(None))
            .label("delivery_count"),
            func.coalesce(func.sum(Delivery.quantity), ZERO).label("quantity"),
            func.coalesce(
                func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO
            ).label("value"),
        )
        .join(Delivery, Delivery.produce_line_id == ProduceLine.id)
        .where(Delivery.delivered_at >= first_instant)
        .group_by(ProduceLine.id, ProduceLine.name, ProduceLine.unit)
        .order_by(
            func.coalesce(
                func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO
            ).desc(),
            ProduceLine.name,
        )
    ).all()

    return [
        DeliveriesByLine(
            produce_line_id=row.id,
            produce_line_name=row.name,
            unit=row.unit,
            count=row.delivery_count,
            quantity=row.quantity,
            value=row.value,
        )
        for row in rows
    ]


def _deliveries_daily(
    db: Session, first_day: date, first_instant: datetime
) -> list[DeliveriesDaily]:
    """
    One bucket per calendar day in the period, zero-filled.

    A chart with holes in it is harder to read than a chart with zeros, and
    the frontend renders the array as given.
    """
    day = func.date(Delivery.delivered_at)
    rows = db.execute(
        select(
            day.label("day"),
            func.count(Delivery.id)
            .filter(Delivery.reversal_of_id.is_(None))
            .label("delivery_count"),
            func.coalesce(
                func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO
            ).label("value"),
        )
        .where(Delivery.delivered_at >= first_instant)
        .group_by(day)
    ).all()

    by_day = {row.day: row for row in rows}

    today = datetime.now(UTC).date()
    buckets: list[DeliveriesDaily] = []
    current = first_day
    while current <= today:
        row = by_day.get(current)
        buckets.append(
            DeliveriesDaily(
                date=current,
                count=row.delivery_count if row else 0,
                value=row.value if row else ZERO,
            )
        )
        current += timedelta(days=1)
    return buckets


# ---------------------------------------------------------------------------
# Recent activity
# ---------------------------------------------------------------------------


def _recent_activity(db: Session) -> list[ActivityItem]:
    deliveries = list(
        db.scalars(
            select(Delivery)
            .order_by(Delivery.delivered_at.desc(), Delivery.id.desc())
            .limit(ACTIVITY_LIMIT)
        ).all()
    )
    payments = list(
        db.scalars(
            select(Payment)
            .order_by(Payment.paid_at.desc(), Payment.id.desc())
            .limit(ACTIVITY_LIMIT)
        ).all()
    )
    deductions = list(
        db.scalars(
            select(Deduction)
            .order_by(Deduction.applied_at.desc(), Deduction.id.desc())
            .limit(ACTIVITY_LIMIT)
        ).all()
    )

    farmer_ids = (
        {d.farmer_id for d in deliveries}
        | {p.farmer_id for p in payments}
        | {x.farmer_id for x in deductions}
    )
    line_ids = {d.produce_line_id for d in deliveries}

    farmers: dict[uuid.UUID, Farmer] = {}
    if farmer_ids:
        farmers = {
            f.id: f for f in db.scalars(select(Farmer).where(Farmer.id.in_(farmer_ids)))
        }

    lines: dict[uuid.UUID, ProduceLine] = {}
    if line_ids:
        lines = {
            line.id: line
            for line in db.scalars(
                select(ProduceLine).where(ProduceLine.id.in_(line_ids))
            )
        }

    items: list[tuple[datetime, ActivityItem]] = []

    for d in deliveries:
        farmer = farmers.get(d.farmer_id)
        items.append(
            (
                d.delivered_at,
                ActivityItem(
                    type=(
                        "delivery_reversal"
                        if d.reversal_of_id is not None
                        else "delivery"
                    ),
                    id=d.id,
                    at=d.delivered_at,
                    description=describe_delivery(d, lines.get(d.produce_line_id)),
                    amount=d.amount,
                    currency=d.currency_snapshot,
                    farmer_id=d.farmer_id,
                    farmer_name=farmer.full_name if farmer else "Unknown farmer",
                ),
            )
        )

    for p in payments:
        farmer = farmers.get(p.farmer_id)
        items.append(
            (
                p.paid_at,
                ActivityItem(
                    type=(
                        "payment_reversal"
                        if p.reversal_of_id is not None
                        else "payment"
                    ),
                    id=p.id,
                    at=p.paid_at,
                    description=describe_payment(p),
                    amount=p.amount,
                    currency=p.currency,
                    farmer_id=p.farmer_id,
                    farmer_name=farmer.full_name if farmer else "Unknown farmer",
                ),
            )
        )

    for x in deductions:
        farmer = farmers.get(x.farmer_id)
        items.append(
            (
                x.applied_at,
                ActivityItem(
                    type=(
                        "deduction_reversal"
                        if x.reversal_of_id is not None
                        else "deduction"
                    ),
                    id=x.id,
                    at=x.applied_at,
                    description=describe_deduction(x),
                    # Withholding reduces the payout, so it reads negative in
                    # the feed for the same reason it does on a statement.
                    amount=-x.amount,
                    currency=x.currency,
                    farmer_id=x.farmer_id,
                    farmer_name=farmer.full_name if farmer else "Unknown farmer",
                ),
            )
        )

    # Newest first. Ties broken by id so the feed is stable across requests.
    items.sort(key=lambda pair: (pair[0], str(pair[1].id)), reverse=True)
    return [item for _, item in items[:ACTIVITY_LIMIT]]


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def build_dashboard_summary(db: Session, period_days: int = 30) -> DashboardSummary:
    first_day, first_instant = _period_bounds(period_days)

    farmers_total, farmers_by_status = _farmers(db)
    (
        outstanding_debt_total,
        available_credit_total,
        deductions_total,
        pending_valuation_count,
    ) = _financial_position(db)
    (
        deliveries_in_period,
        deliveries_value_in_period,
        payments_in_period,
        payments_value_in_period,
        deductions_in_period,
        deductions_value_in_period,
    ) = _period_totals(db, first_instant)

    return DashboardSummary(
        generated_at=datetime.now(UTC),
        period_days=period_days,
        currency=settings.default_currency,
        farmers_total=farmers_total,
        farmers_by_status=farmers_by_status,
        deliveries_in_period=deliveries_in_period,
        deliveries_value_in_period=deliveries_value_in_period,
        payments_in_period=payments_in_period,
        payments_value_in_period=payments_value_in_period,
        deductions_in_period=deductions_in_period,
        deductions_value_in_period=deductions_value_in_period,
        outstanding_debt_total=outstanding_debt_total,
        available_credit_total=available_credit_total,
        deductions_total=deductions_total,
        net_payable_total=(
            outstanding_debt_total - available_credit_total - deductions_total
        ),
        pending_valuation_count=pending_valuation_count,
        deliveries_by_line=_deliveries_by_line(db, first_instant),
        deliveries_daily=_deliveries_daily(db, first_day, first_instant),
        recent_activity=_recent_activity(db),
    )
