"""
Ledger computations.

This module is the single source of truth for "what does this farmer owe /
have on account?". Balance (B.6) and statement (B.8) both call these
functions, so they cannot disagree.

Conventions:
- Amounts are Decimal. Never float.
- Reversals are encoded as negative amounts in the same table. We sum ALL
  rows (normal and reversal) and let the sign do the work — do NOT filter
  on reversal_of_id in aggregation. Filtering would give the wrong total
  for a delivery that has been reversed.

Definitions (see DECISIONS.md D-019):
- outstanding_debt: unpaid value of valued, non-deleted deliveries.
- allocated_to_deliveries: sum of net allocations against this farmer's
  deliveries. Informational only — it is already reflected in
  outstanding_debt.
- available_credit: money received (net of payment reversals) MINUS money
  allocated to deliveries. This is money the co-op holds on the farmer's
  behalf.
- pending_valuation_deliveries: count of deliveries with rate_snapshot
  NULL. Disclosed so admins can act; excluded from outstanding_debt
  because they have no value yet.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.deduction import Deduction
from app.models.delivery import Delivery
from app.models.payment import Payment, PaymentAllocation

ZERO = Decimal("0.0000")


@dataclass(frozen=True)
class FarmerBalance:
    outstanding_debt: Decimal  # co-op still owes the farmer for deliveries
    # informational; already reflected in outstanding_debt
    allocated_to_deliveries: Decimal
    # money on account, available to allocate to future deliveries
    available_credit: Decimal
    pending_valuation_deliveries: int  # count; not in outstanding_debt
    # total withheld from this member (charges net of their reversals)
    deductions_total: Decimal
    # what the co-op would actually hand over today. Negative means the
    # member owes the co-op — arrears, which deductions make reachable.
    net_payable: Decimal


def _sum_delivery_value(db: Session, farmer_id: uuid.UUID) -> Decimal:
    """
    Sum of (quantity * rate_snapshot) for every valued delivery of this
    farmer, INCLUDING reversals (which are negative rows). Deliveries with
    NULL rate_snapshot are excluded — they have no value yet.
    """
    stmt = (
        select(
            func.coalesce(func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO)
        )
        .where(Delivery.farmer_id == farmer_id)
        .where(Delivery.rate_snapshot.is_not(None))
    )
    value = db.scalar(stmt)
    return value if value is not None else ZERO


def _sum_net_allocations_for_farmer(db: Session, farmer_id: uuid.UUID) -> Decimal:
    """
    Sum of every PaymentAllocation amount whose delivery belongs to this
    farmer, INCLUDING allocation reversals (negative rows).
    """
    stmt = (
        select(func.coalesce(func.sum(PaymentAllocation.amount), ZERO))
        .join(Delivery, Delivery.id == PaymentAllocation.delivery_id)
        .where(Delivery.farmer_id == farmer_id)
    )
    value = db.scalar(stmt)
    return value if value is not None else ZERO


def _sum_net_payments(db: Session, farmer_id: uuid.UUID) -> Decimal:
    """
    Sum of every Payment amount for this farmer, INCLUDING payment reversals
    (negative rows).
    """
    stmt = select(func.coalesce(func.sum(Payment.amount), ZERO)).where(
        Payment.farmer_id == farmer_id
    )
    value = db.scalar(stmt)
    return value if value is not None else ZERO


def _sum_net_deductions(db: Session, farmer_id: uuid.UUID) -> Decimal:
    """
    Total withheld from this farmer, INCLUDING reversals (negative rows).

    Deliberately not filtered: a deduction that was withdrawn must stop
    counting, and the signed row makes that automatic.
    """
    value = db.scalar(
        select(func.coalesce(func.sum(Deduction.amount), ZERO)).where(
            Deduction.farmer_id == farmer_id
        )
    )
    return value if value is not None else ZERO


def _count_pending_valuation(db: Session, farmer_id: uuid.UUID) -> int:
    """Number of deliveries awaiting valuation (rate_snapshot IS NULL)."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Delivery)
            .where(Delivery.farmer_id == farmer_id)
            .where(Delivery.rate_snapshot.is_(None))
        )
        or 0
    )


def compute_balance(db: Session, farmer_id: uuid.UUID) -> FarmerBalance:
    """
    Compute the farmer's financial position from the ledger.

    No filtering on reversal_of_id anywhere in the sums — reversal rows are
    signed (negative) and aggregate correctly. See module docstring.
    """
    total_delivery_value = _sum_delivery_value(db, farmer_id)
    total_allocated = _sum_net_allocations_for_farmer(db, farmer_id)
    total_paid = _sum_net_payments(db, farmer_id)
    total_deductions = _sum_net_deductions(db, farmer_id)
    pending = _count_pending_valuation(db, farmer_id)

    outstanding_debt = total_delivery_value - total_allocated
    available_credit = total_paid - total_allocated
    # Allocations cancel: what is handed over is produce value, less money
    # already paid, less what was withheld.
    net_payable = outstanding_debt - available_credit - total_deductions

    return FarmerBalance(
        outstanding_debt=outstanding_debt,
        allocated_to_deliveries=total_allocated,
        available_credit=available_credit,
        pending_valuation_deliveries=pending,
        deductions_total=total_deductions,
        net_payable=net_payable,
    )


def compute_balance_at(
    db: Session,
    farmer_id: uuid.UUID,
    as_of: datetime,
    inclusive: bool = True,
) -> FarmerBalance:
    """Time-bounded variant of compute_balance. Used by the statement service."""
    if inclusive:
        d_cond = Delivery.delivered_at <= as_of
        p_cond = Payment.paid_at <= as_of
        x_cond = Deduction.applied_at <= as_of
    else:
        d_cond = Delivery.delivered_at < as_of
        p_cond = Payment.paid_at < as_of
        x_cond = Deduction.applied_at < as_of

    delivery_value = (
        db.scalar(
            select(
                func.coalesce(
                    func.sum(Delivery.quantity * Delivery.rate_snapshot), ZERO
                )
            )
            .where(Delivery.farmer_id == farmer_id)
            .where(Delivery.rate_snapshot.is_not(None))
            .where(d_cond)
        )
        or ZERO
    )

    allocations = (
        db.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), ZERO))
            .join(Payment, Payment.id == PaymentAllocation.payment_id)
            .where(Payment.farmer_id == farmer_id)
            .where(p_cond)
        )
        or ZERO
    )

    payments = (
        db.scalar(
            select(func.coalesce(func.sum(Payment.amount), ZERO))
            .where(Payment.farmer_id == farmer_id)
            .where(p_cond)
        )
        or ZERO
    )

    deductions = (
        db.scalar(
            select(func.coalesce(func.sum(Deduction.amount), ZERO))
            .where(Deduction.farmer_id == farmer_id)
            .where(x_cond)
        )
        or ZERO
    )

    debt = delivery_value - allocations
    credit = payments - allocations

    return FarmerBalance(
        outstanding_debt=debt,
        allocated_to_deliveries=allocations,
        available_credit=credit,
        pending_valuation_deliveries=0,
        deductions_total=deductions,
        net_payable=debt - credit - deductions,
    )
