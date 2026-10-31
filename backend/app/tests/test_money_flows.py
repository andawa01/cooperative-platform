"""
Integration tests for critical money flows in ShambaTrack.

These tests exercise the service layer directly (not HTTP endpoints) to
verify end-to-end financial correctness: delivery valuation, payment
allocation, reversals, idempotency, and balance computation.

The `db` fixture uses savepoint mode, so service commits become savepoints
and test isolation is automatic — each test runs in a rolled-back transaction.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.payment import PaymentAllocation, PaymentMethod
from app.models.produce import Rate
from app.schemas.delivery import DeliveryCreate
from app.schemas.payment import AllocationInput, PaymentCreate
from app.services import delivery as delivery_service
from app.services import ledger as ledger_service
from app.services import payment as payment_service

# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------

# A date comfortably within the rate fixture's effective range
# (effective_from = 2025-01-01, effective_to = None).
DELIVERED_AT = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)
PAID_AT = datetime(2025, 6, 1, 12, 0, tzinfo=UTC)

# The rate fixture sets rate_per_unit = 50.0000 KES, so 100 kg → 5000 KES.
DEFAULT_QUANTITY = Decimal("100")
DEFAULT_RATE = Decimal("50.0000")
DEFAULT_DELIVERY_VALUE = Decimal("5000")  # 100 * 50


def _delivery(farmer_id, produce_line_id, **kwargs):
    """Build a DeliveryCreate with sensible defaults."""
    defaults = dict(
        farmer_id=farmer_id,
        produce_line_id=produce_line_id,
        quantity=DEFAULT_QUANTITY,
        delivered_at=DELIVERED_AT,
    )
    defaults.update(kwargs)
    return DeliveryCreate(**defaults)


def _payment(farmer_id, amount, **kwargs):
    """Build a PaymentCreate with sensible defaults."""
    defaults = dict(
        farmer_id=farmer_id,
        amount=amount,
        currency="KES",
        method=PaymentMethod.CASH,
        reference=None,
        paid_at=PAID_AT,
        allocations=None,
        idempotency_key=str(uuid.uuid4()),
        notes=None,
    )
    defaults.update(kwargs)
    return PaymentCreate(**defaults)


def _net_allocated_for_delivery(db, delivery_id) -> Decimal:
    """Sum of ALL allocations against a delivery, including reversals."""
    total = db.scalar(
        select(func.coalesce(func.sum(PaymentAllocation.amount), Decimal("0"))).where(
            PaymentAllocation.delivery_id == delivery_id
        )
    )
    return total if total is not None else Decimal("0")


# ---------------------------------------------------------------------------
# 1. Full delivery → payment → balance flow
# ---------------------------------------------------------------------------


class TestFullDeliveryPaymentFlow:
    """Record a delivery (with rate), record a payment with allocations
    against it, and verify the farmer's balance reflects the correct
    outstanding debt and allocations."""

    def test_full_flow(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery: 100 kg @ 50 KES/kg = 5000 KES ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )
        assert delivery.rate_snapshot == DEFAULT_RATE
        assert delivery.amount == DEFAULT_DELIVERY_VALUE

        # Balance after delivery: full debt, nothing allocated or paid.
        bal = ledger_service.compute_balance(db, farmer.id)
        assert bal.outstanding_debt == DEFAULT_DELIVERY_VALUE
        assert bal.allocated_to_deliveries == Decimal("0")
        assert bal.available_credit == Decimal("0")
        assert bal.pending_valuation_deliveries == 0

        # --- Payment: 5000 KES, fully allocated to the delivery ---
        payment, replayed = payment_service.record_payment(
            db,
            _payment(
                farmer.id,
                DEFAULT_DELIVERY_VALUE,
                allocations=[
                    AllocationInput(
                        delivery_id=delivery.id, amount=DEFAULT_DELIVERY_VALUE
                    )
                ],
            ),
            clerk,
        )
        assert not replayed  # first time, not a replay

        # --- Balance after payment: debt settled ---
        bal = ledger_service.compute_balance(db, farmer.id)
        assert bal.outstanding_debt == Decimal("0")
        assert bal.allocated_to_deliveries == DEFAULT_DELIVERY_VALUE
        assert bal.available_credit == Decimal("0")
        assert bal.pending_valuation_deliveries == 0

        # The payment should have exactly one allocation matching the delivery.
        allocs = payment_service.list_allocations_for_payment(db, payment.id)
        assert len(allocs) == 1
        assert allocs[0].delivery_id == delivery.id
        assert allocs[0].amount == DEFAULT_DELIVERY_VALUE


# ---------------------------------------------------------------------------
# 2. Delivery with pending valuation
# ---------------------------------------------------------------------------


class TestPendingValuation:
    """Record a delivery without a rate (rate_snapshot=NULL), then value
    it via value_delivery(), and verify the balance updates."""

    def test_pending_valuation(self, db, clerk, farmer, produce_line, admin):
        # No `rate` fixture is requested, so no rate exists for this produce
        # line at delivered_at. The delivery should be recorded with
        # rate_snapshot = NULL (pending valuation).
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )
        assert delivery.rate_snapshot is None
        assert delivery.amount is None  # unvalued deliveries have no amount

        # Balance: no valued deliveries → zero debt, one pending valuation.
        bal = ledger_service.compute_balance(db, farmer.id)
        assert bal.outstanding_debt == Decimal("0")
        assert bal.pending_valuation_deliveries == 1

        # --- Create a rate effective from before delivered_at ---
        # value_delivery() looks up the rate effective on the delivery's
        # delivered_at at the moment of valuation. We need a rate that covers
        # 2025-06-01 to exist now.
        new_rate = Rate(
            produce_line_id=produce_line.id,
            rate_per_unit=DEFAULT_RATE,
            currency="KES",
            effective_from=date(2025, 1, 1),
            effective_to=None,
            created_by_id=admin.id,
        )
        db.add(new_rate)
        db.flush()

        # --- Value the pending delivery ---
        valued = delivery_service.value_delivery(db, delivery.id, clerk)
        assert valued.rate_snapshot == DEFAULT_RATE
        assert valued.amount == DEFAULT_DELIVERY_VALUE

        # Balance: now the delivery is valued → debt = 5000, no pending.
        bal = ledger_service.compute_balance(db, farmer.id)
        assert bal.outstanding_debt == DEFAULT_DELIVERY_VALUE
        assert bal.pending_valuation_deliveries == 0


# ---------------------------------------------------------------------------
# 3. Payment reversal flow
# ---------------------------------------------------------------------------


class TestPaymentReversal:
    """Record delivery + payment, then reverse the payment. Verify balance
    returns to pre-payment state and allocations are reversed."""

    def test_payment_reversal(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery worth 5000 ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )

        # Pre-payment balance.
        pre_bal = ledger_service.compute_balance(db, farmer.id)
        assert pre_bal.outstanding_debt == DEFAULT_DELIVERY_VALUE

        # --- Payment of 3000 allocated to the delivery ---
        payment, _ = payment_service.record_payment(
            db,
            _payment(
                farmer.id,
                Decimal("3000"),
                allocations=[
                    AllocationInput(delivery_id=delivery.id, amount=Decimal("3000"))
                ],
            ),
            clerk,
        )

        # Post-payment balance: 2000 debt remaining, 3000 allocated.
        mid_bal = ledger_service.compute_balance(db, farmer.id)
        assert mid_bal.outstanding_debt == Decimal("2000")
        assert mid_bal.allocated_to_deliveries == Decimal("3000")
        assert mid_bal.available_credit == Decimal("0")

        # --- Reverse the payment ---
        reversal = payment_service.reverse_payment(
            db, payment.id, "corrective reversal", clerk
        )
        assert reversal.amount == Decimal("-3000")
        assert reversal.reversal_of_id == payment.id

        # Balance returns to pre-payment state.
        post_bal = ledger_service.compute_balance(db, farmer.id)
        assert post_bal.outstanding_debt == DEFAULT_DELIVERY_VALUE  # back to 5000
        assert post_bal.allocated_to_deliveries == Decimal("0")  # allocations reversed
        assert post_bal.available_credit == Decimal("0")  # net payment = 0

        # The reversal payment should carry a negative allocation mirroring
        # the original, confirming allocations are reversed.
        reversal_allocs = payment_service.list_allocations_for_payment(db, reversal.id)
        assert len(reversal_allocs) == 1
        assert reversal_allocs[0].amount == Decimal("-3000")
        assert reversal_allocs[0].reversal_of_id is not None

        # Net allocation for the delivery should be zero (original + reversal).
        assert _net_allocated_for_delivery(db, delivery.id) == Decimal("0")


# ---------------------------------------------------------------------------
# 4. Delivery reversal flow
# ---------------------------------------------------------------------------


class TestDeliveryReversal:
    """Record delivery + payment (allocated), then reverse the delivery.
    Verify allocations cascade-reverse and balance updates."""

    def test_delivery_reversal(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery worth 5000 ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )

        # --- Payment of 5000 fully allocated to the delivery ---
        payment, _ = payment_service.record_payment(
            db,
            _payment(
                farmer.id,
                DEFAULT_DELIVERY_VALUE,
                allocations=[
                    AllocationInput(
                        delivery_id=delivery.id, amount=DEFAULT_DELIVERY_VALUE
                    )
                ],
            ),
            clerk,
        )

        # Pre-reversal balance: fully settled.
        bal = ledger_service.compute_balance(db, farmer.id)
        assert bal.outstanding_debt == Decimal("0")
        assert bal.allocated_to_deliveries == DEFAULT_DELIVERY_VALUE
        assert bal.available_credit == Decimal("0")

        # --- Reverse the delivery ---
        reversal = delivery_service.reverse_delivery(
            db, delivery.id, "wrong entry", clerk
        )
        assert reversal.quantity == -DEFAULT_QUANTITY  # -100
        assert reversal.reversal_of_id == delivery.id
        assert reversal.rate_snapshot == DEFAULT_RATE

        # Post-reversal balance:
        # - Delivery value nets to 0 (original 5000 + negative reversal -5000).
        # - Allocations cascade-reverse → net allocation = 0.
        # - Payment still exists (5000) but is now unallocated
        #   → available_credit = 5000 (money the co-op holds on farmer's behalf).
        post_bal = ledger_service.compute_balance(db, farmer.id)
        assert post_bal.outstanding_debt == Decimal("0")
        assert post_bal.allocated_to_deliveries == Decimal("0")
        assert post_bal.available_credit == DEFAULT_DELIVERY_VALUE  # 5000

        # Verify the allocation was cascade-reversed: the original payment
        # now has both the original positive allocation and its negative
        # reversal allocation, netting to zero.
        all_allocs = payment_service.list_allocations_for_payment(db, payment.id)
        assert len(all_allocs) == 2  # original + reversal
        net = sum(a.amount for a in all_allocs)
        assert net == Decimal("0")

        # Net allocation for the delivery should also be zero.
        assert _net_allocated_for_delivery(db, delivery.id) == Decimal("0")


# ---------------------------------------------------------------------------
# 5. Idempotency replay
# ---------------------------------------------------------------------------


class TestIdempotency:
    """Record a payment with an idempotency key, then replay with the same
    key + same body (returns same payment, no duplicate). Then replay with
    same key + different body (raises IdempotencyConflict)."""

    def test_idempotency_replay(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery worth 5000 ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )

        idem_key = str(uuid.uuid4())

        # --- First call: create the payment ---
        p1, replayed1 = payment_service.record_payment(
            db,
            _payment(
                farmer.id,
                DEFAULT_DELIVERY_VALUE,
                allocations=[
                    AllocationInput(
                        delivery_id=delivery.id, amount=DEFAULT_DELIVERY_VALUE
                    )
                ],
                idempotency_key=idem_key,
            ),
            clerk,
        )
        assert not replayed1  # fresh creation

        # --- Replay with same key + same body → same payment, no duplicate ---
        p2, replayed2 = payment_service.record_payment(
            db,
            _payment(
                farmer.id,
                DEFAULT_DELIVERY_VALUE,
                allocations=[
                    AllocationInput(
                        delivery_id=delivery.id, amount=DEFAULT_DELIVERY_VALUE
                    )
                ],
                idempotency_key=idem_key,
            ),
            clerk,
        )
        assert replayed2  # this is a replay
        assert p2.id == p1.id  # same payment, not a duplicate

        # Verify only one payment exists for this farmer.
        payments, total = payment_service.list_payments(
            db, farmer_id=farmer.id, include_reversals=True
        )
        assert total == 1

        # --- Replay with same key + different body → IdempotencyConflict ---
        with pytest.raises(payment_service.IdempotencyConflict):
            payment_service.record_payment(
                db,
                _payment(
                    farmer.id,
                    Decimal("3000"),  # different amount → different fingerprint
                    allocations=[
                        AllocationInput(delivery_id=delivery.id, amount=Decimal("3000"))
                    ],
                    idempotency_key=idem_key,
                ),
                clerk,
            )


# ---------------------------------------------------------------------------
# 6. Partial payment
# ---------------------------------------------------------------------------


class TestPartialPayment:
    """Record a delivery worth 5000, pay 3000 (partial), verify remaining
    debt is 2000."""

    def test_partial_payment(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery worth 5000 ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )

        # --- Partial payment of 3000 ---
        payment, _ = payment_service.record_payment(
            db,
            _payment(
                farmer.id,
                Decimal("3000"),
                allocations=[
                    AllocationInput(delivery_id=delivery.id, amount=Decimal("3000"))
                ],
            ),
            clerk,
        )

        # Remaining debt should be 2000 (5000 - 3000).
        bal = ledger_service.compute_balance(db, farmer.id)
        assert bal.outstanding_debt == Decimal("2000")
        assert bal.allocated_to_deliveries == Decimal("3000")
        assert bal.available_credit == Decimal("0")  # all paid money allocated

        # Verify the allocation amount on the payment.
        allocs = payment_service.list_allocations_for_payment(db, payment.id)
        assert len(allocs) == 1
        assert allocs[0].amount == Decimal("3000")


# ---------------------------------------------------------------------------
# 7. Over-allocation rejection
# ---------------------------------------------------------------------------


class TestOverAllocation:
    """Try to allocate more than the payment amount, verify
    AllocationsExceedPayment is raised."""

    def test_over_allocation_rejected(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery worth 5000 ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )

        # Payment of 3000 but allocation of 4000 (exceeds payment amount).
        # The allocation (4000) fits within the delivery's remaining value
        # (5000), but the total allocations (4000) exceed the payment amount
        # (3000) → AllocationsExceedPayment.
        with pytest.raises(payment_service.AllocationsExceedPayment):
            payment_service.record_payment(
                db,
                _payment(
                    farmer.id,
                    Decimal("3000"),
                    allocations=[
                        AllocationInput(delivery_id=delivery.id, amount=Decimal("4000"))
                    ],
                ),
                clerk,
            )


# ---------------------------------------------------------------------------
# 8. Duplicate allocation rejection
# ---------------------------------------------------------------------------


class TestDuplicateAllocation:
    """Try to allocate the same delivery twice in one payment, verify
    DuplicateAllocationDelivery is raised."""

    def test_duplicate_allocation_rejected(self, db, clerk, farmer, produce_line, rate):
        # --- Delivery ---
        delivery = delivery_service.record_delivery(
            db, _delivery(farmer.id, produce_line.id), clerk
        )

        # Payment with two allocations targeting the same delivery.
        # Even though the total (5000) fits within both the payment amount
        # and the delivery's remaining value, the duplicate delivery_id
        # triggers DuplicateAllocationDelivery.
        with pytest.raises(payment_service.DuplicateAllocationDelivery):
            payment_service.record_payment(
                db,
                _payment(
                    farmer.id,
                    DEFAULT_DELIVERY_VALUE,
                    allocations=[
                        AllocationInput(
                            delivery_id=delivery.id, amount=Decimal("2500")
                        ),
                        AllocationInput(
                            delivery_id=delivery.id, amount=Decimal("2500")
                        ),
                    ],
                ),
                clerk,
            )
