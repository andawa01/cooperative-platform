"""
Statement service. See module docstring...
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.delivery import Delivery
from app.models.payment import Payment, PaymentAllocation
from app.models.produce import ProduceLine
from app.schemas.statement import (
    FarmerStatementResponse,
    StatementEntry,
    StatementOpening,
)
from app.services import ledger as ledger_service

# ---------------------------------------------------------------------------
# Event assembly
# ---------------------------------------------------------------------------


def describe_delivery(delivery: Delivery, line: ProduceLine | None) -> str:
    if delivery.reversal_of_id is not None:
        reason = (delivery.notes or "").removeprefix("[reversal] ").strip()
        base = "Delivery reversal"
        return f"{base}: {reason}" if reason else base
    if line is None:
        return f"Delivery {delivery.quantity} (unknown line)"
    if delivery.rate_snapshot is None:
        return f"{line.name} {delivery.quantity} {line.unit} (rate pending)"
    return (
        f"{line.name} {delivery.quantity} {line.unit} "
        f"@ {delivery.rate_snapshot} {delivery.currency_snapshot}"
    )


def describe_payment(payment: Payment) -> str:
    if payment.reversal_of_id is not None:
        reason = (payment.notes or "").removeprefix("[reversal] ").strip()
        base = "Payment reversal"
        return f"{base}: {reason}" if reason else base
    ref = f" {payment.reference}" if payment.reference else ""
    return f"{payment.method}{ref} {payment.amount} {payment.currency}"


def _compute_deltas(
    delivery: Delivery | None,
    payment: Payment | None,
    reversed_allocations_by_delivery: dict[uuid.UUID, Decimal],
) -> tuple[Decimal, Decimal]:
    """
    Return (debt_delta, credit_delta) for one top-level event.

    reversed_allocations_by_delivery: for a delivery_reversal event, sum of
    the (positive) amounts of the allocations that were reversed by its
    cascade, keyed by the original delivery id.
    """
    if delivery is not None:
        if delivery.reversal_of_id is None:
            # Normal delivery: increases debt.
            amount = (delivery.rate_snapshot or Decimal("0")) * delivery.quantity
            return (amount, Decimal("0"))
        else:
            # Delivery reversal: debt reduced by original amount, minus the
            # un-doing of allocations (since those allocations also disappear).
            # Net effect on debt: -orig_amount + reversed_alloc_sum
            # Net effect on credit: +reversed_alloc_sum
            orig_amount = abs(
                (delivery.rate_snapshot or Decimal("0")) * delivery.quantity
            )
            reversed_alloc = reversed_allocations_by_delivery.get(
                delivery.reversal_of_id, Decimal("0")
            )
            return (-orig_amount + reversed_alloc, reversed_alloc)

    if payment is not None:
        if payment.reversal_of_id is None:
            # Normal payment: credit goes up by amount not allocated; debt
            # goes down by allocations. We compute allocations at build time
            # from the payment_allocations we loaded.
            # handled by caller
            raise RuntimeError("payment delta handled by caller")
        else:
            raise RuntimeError("payment delta handled by caller")

    raise RuntimeError("event has neither delivery nor payment")


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_statement(
    db: Session,
    farmer_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> FarmerStatementResponse:
    # Opening pair: everything strictly before `start`.
    opening = ledger_service.compute_balance_at(
        db, farmer_id, as_of=start, inclusive=False
    )
    opening_debt = opening.outstanding_debt
    opening_credit = opening.available_credit

    # Load events in [start, end].
    deliveries = list(
        db.scalars(
            select(Delivery)
            .where(Delivery.farmer_id == farmer_id)
            .where(Delivery.delivered_at >= start)
            .where(Delivery.delivered_at <= end)
        ).all()
    )
    payments = list(
        db.scalars(
            select(Payment)
            .where(Payment.farmer_id == farmer_id)
            .where(Payment.paid_at >= start)
            .where(Payment.paid_at <= end)
        ).all()
    )

    # Load all allocations relevant to any of these events.
    delivery_ids = [d.id for d in deliveries]
    payment_ids = [p.id for p in payments]

    allocation_conditions = []
    if delivery_ids:
        allocation_conditions.append(PaymentAllocation.delivery_id.in_(delivery_ids))
    if payment_ids:
        allocation_conditions.append(PaymentAllocation.payment_id.in_(payment_ids))

    allocations: list[PaymentAllocation] = []
    if allocation_conditions:
        allocations = list(
            db.scalars(select(PaymentAllocation).where(*allocation_conditions)).all()
        )

    # Build allocation indexes.
    # allocations_by_payment: {payment_id: net_alloc_sum}
    # reversed_alloc_by_delivery_reversal: {reversal_delivery_id: amount}
    allocations_by_payment: dict[uuid.UUID, Decimal] = {}
    for a in allocations:
        allocations_by_payment[a.payment_id] = (
            allocations_by_payment.get(a.payment_id, Decimal("0")) + a.amount
        )

    # For delivery reversals: their cascade creates PaymentAllocation rows with
    # reversal_of_id pointing at the original allocations and delivery_id equal
    # to the ORIGINAL delivery. We need "for original delivery X, how much was
    # reversed". We can find this by looking at allocations with
    # reversal_of_id NOT NULL and delivery_id = X.
    reversed_alloc_by_original_delivery: dict[uuid.UUID, Decimal] = {}
    for a in allocations:
        if a.reversal_of_id is not None:
            reversed_alloc_by_original_delivery[a.delivery_id] = (
                reversed_alloc_by_original_delivery.get(a.delivery_id, Decimal("0"))
                + abs(a.amount)
            )

    # Load produce lines for descriptions.
    line_ids = {d.produce_line_id for d in deliveries}
    lines: dict[uuid.UUID, ProduceLine] = {}
    if line_ids:
        for line in db.scalars(select(ProduceLine).where(ProduceLine.id.in_(line_ids))):
            lines[line.id] = line

    # Build event tuples: (date, kind, obj).
    events = []
    for d in deliveries:
        events.append((d.delivered_at, "delivery", d))
    for p in payments:
        events.append((p.paid_at, "payment", p))

    # Sort: by date, then delivery before payment (deterministic tie-break),
    # then by id for full determinism.
    def sort_key(ev):
        dt, kind, obj = ev
        kind_rank = 0 if kind == "delivery" else 1
        return (dt, kind_rank, str(obj.id))

    events.sort(key=sort_key)

    # Walk and apply.
    current_debt = opening_debt
    current_credit = opening_credit
    entries: list[StatementEntry] = []

    for dt, kind, obj in events:
        if kind == "delivery":
            d: Delivery = obj
            line = lines.get(d.produce_line_id)
            description = describe_delivery(d, line)
            if d.reversal_of_id is None:
                amount = (d.rate_snapshot or Decimal("0")) * d.quantity
                debt_delta = amount
                credit_delta = Decimal("0")
            else:
                orig_amount = abs((d.rate_snapshot or Decimal("0")) * d.quantity)
                reversed_alloc = reversed_alloc_by_original_delivery.get(
                    d.reversal_of_id, Decimal("0")
                )
                debt_delta = -orig_amount + reversed_alloc
                credit_delta = reversed_alloc
                amount = -orig_amount

            current_debt += debt_delta
            current_credit += credit_delta
            entries.append(
                StatementEntry(
                    date=dt,
                    type=(
                        "delivery" if d.reversal_of_id is None else "delivery_reversal"
                    ),
                    amount=amount,
                    description=description,
                    delivery_id=d.id,
                    reversal_of_id=d.reversal_of_id,
                    debt_after=current_debt,
                    credit_after=current_credit,
                )
            )
        else:
            p: Payment = obj
            description = describe_payment(p)
            net_alloc = allocations_by_payment.get(p.id, Decimal("0"))
            if p.reversal_of_id is None:
                # Normal payment: credit += (amount - net_alloc), debt -= net_alloc
                debt_delta = -net_alloc
                credit_delta = p.amount - net_alloc
                amount = p.amount
            else:
                # Payment reversal: net_alloc here is negative (the reversal
                # allocation). credit += (p.amount - net_alloc) but p.amount
                # is already negative...
                # Let's reason: reversal payment amount = -orig. Its allocations
                # (from the cascade) are also negative; their sum is net_alloc
                # (a negative number, equal to -orig_allocated).
                # Effect on debt: -net_alloc = +orig_allocated → debt increases.
                # Effect on credit: p.amount - net_alloc = -orig + orig_allocated
                #  = -(orig - orig_allocated) = -(credit from original) ✓
                debt_delta = -net_alloc
                credit_delta = p.amount - net_alloc
                amount = p.amount

            current_debt += debt_delta
            current_credit += credit_delta
            entries.append(
                StatementEntry(
                    date=dt,
                    type="payment" if p.reversal_of_id is None else "payment_reversal",
                    amount=amount,
                    description=description,
                    payment_id=p.id,
                    reversal_of_id=p.reversal_of_id,
                    debt_after=current_debt,
                    credit_after=current_credit,
                )
            )

    return FarmerStatementResponse(
        farmer_id=farmer_id,
        start=start,
        end=end,
        currency="KES",
        opening=StatementOpening(
            outstanding_debt=opening_debt,
            available_credit=opening_credit,
        ),
        entries=entries,
        closing=StatementOpening(
            outstanding_debt=current_debt,
            available_credit=current_credit,
        ),
    )
