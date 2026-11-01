"""
Statement service.

A statement is the chronological story of a farmer's position: deliveries
raise what the co-op owes them, payments settle it, and deductions withhold
from it. All three are top-level events here — nothing is nested — so the
screen can render one flat, ordered list.

Reversals appear as their own entries rather than cancelling the original, the
same choice the delivery and payment ledgers make (D-019): a statement is an
audit trail, and history that silently disappears is not auditable.

The closing figures MUST equal /farmers/{id}/balance when the range runs
through today. There is a pytest for exactly that.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deduction import Deduction
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


def describe_deduction(deduction: Deduction) -> str:
    label = deduction.reason_code.replace("_", " ")
    if deduction.reversal_of_id is not None:
        reason = (deduction.notes or "").removeprefix("[reversal] ").strip()
        base = f"Deduction reversal: {label}"
        return f"{base}: {reason}" if reason else base
    ref = f" ({deduction.reference})" if deduction.reference else ""
    return f"{label} {deduction.amount} {deduction.currency}{ref}"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_statement(
    db: Session,
    farmer_id: uuid.UUID,
    start: datetime,
    end: datetime,
) -> FarmerStatementResponse:
    # Opening position: everything strictly before `start`.
    opening = ledger_service.compute_balance_at(
        db, farmer_id, as_of=start, inclusive=False
    )
    opening_debt = opening.outstanding_debt
    opening_credit = opening.available_credit
    opening_deductions = opening.deductions_total

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
    deductions = list(
        db.scalars(
            select(Deduction)
            .where(Deduction.farmer_id == farmer_id)
            .where(Deduction.applied_at >= start)
            .where(Deduction.applied_at <= end)
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
    # reversed_alloc_by_original_delivery: {original_delivery_id: amount}
    allocations_by_payment: dict[uuid.UUID, Decimal] = {}
    for a in allocations:
        allocations_by_payment[a.payment_id] = (
            allocations_by_payment.get(a.payment_id, Decimal("0")) + a.amount
        )

    # For delivery reversals: their cascade creates PaymentAllocation rows with
    # reversal_of_id pointing at the original allocations and delivery_id equal
    # to the ORIGINAL delivery. We need "for original delivery X, how much was
    # reversed".
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
    for x in deductions:
        events.append(
            (
                x.applied_at,
                "deduction" if x.reversal_of_id is None else "deduction_reversal",
                x,
            )
        )

    # Sort: by date, then by kind, then by id for full determinism.
    # A reversal copies its original's `applied_at`, so on the tie it must
    # come after the charge it undoes — otherwise a statement reads "withheld
    # -250, withheld +250" and the running total dips below zero for no reason
    # the reader can see.
    kind_rank = {
        "delivery": 0,
        "payment": 1,
        "deduction": 2,
        "deduction_reversal": 3,
    }

    def sort_key(ev):
        dt, kind, obj = ev
        return (dt, kind_rank[kind], str(obj.id))

    events.sort(key=sort_key)

    # Walk and apply.
    current_debt = opening_debt
    current_credit = opening_credit
    current_deductions = opening_deductions
    entries: list[StatementEntry] = []

    def net() -> Decimal:
        return current_debt - current_credit - current_deductions

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
                    deductions_after=current_deductions,
                    net_after=net(),
                )
            )
        elif kind == "payment":
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
                # allocation). Its allocations are negative too, summing to
                # net_alloc = -orig_allocated.
                # Effect on debt: -net_alloc → debt increases.
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
                    deductions_after=current_deductions,
                    net_after=net(),
                )
            )
        else:
            x: Deduction = obj
            # A deduction does not touch debt or credit — it withholds from the
            # settlement. It only moves the withheld total.
            current_deductions += x.amount
            entries.append(
                StatementEntry(
                    date=dt,
                    # Shown negative: a charge reduces what the member receives.
                    type=(
                        "deduction"
                        if x.reversal_of_id is None
                        else "deduction_reversal"
                    ),
                    amount=-x.amount,
                    description=describe_deduction(x),
                    deduction_id=x.id,
                    reversal_of_id=x.reversal_of_id,
                    debt_after=current_debt,
                    credit_after=current_credit,
                    deductions_after=current_deductions,
                    net_after=net(),
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
            deductions_total=opening_deductions,
            net_payable=opening_debt - opening_credit - opening_deductions,
        ),
        entries=entries,
        closing=StatementOpening(
            outstanding_debt=current_debt,
            available_credit=current_credit,
            deductions_total=current_deductions,
            net_payable=net(),
        ),
    )
