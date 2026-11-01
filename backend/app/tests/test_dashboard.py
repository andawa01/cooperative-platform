"""
Dashboard tests.

The dashboard is an aggregation of the ledger, so the test that earns its
keep is the consistency invariant: the cooperative-wide totals must equal
the sum of every farmer's balance. If those two ever diverge, a manager is
reading a number that no farmer's statement would corroborate.

We also pin the response contract the frontend depends on (field names,
Decimal-as-string, date format) and the period window.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.security import create_access_token
from app.models.delivery import Delivery
from app.models.farmer import Farmer, FarmerStatus
from app.models.payment import Payment, PaymentAllocation
from app.services import ledger as ledger_service


def _auth_header(user) -> dict:
    tok = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {tok}"}


def _add_delivery(db, farmer, produce_line, actor, *, quantity, rate, at):
    d = Delivery(
        farmer_id=farmer.id,
        produce_line_id=produce_line.id,
        quantity=Decimal(quantity),
        delivered_at=at,
        recorded_at=at,
        recorded_by_id=actor.id,
        rate_snapshot=Decimal(rate) if rate is not None else None,
        currency_snapshot="KES",
    )
    db.add(d)
    db.flush()
    return d


def _add_payment(db, farmer, actor, *, amount, at, key=None):
    p = Payment(
        farmer_id=farmer.id,
        amount=Decimal(amount),
        currency="KES",
        method="cash",
        paid_at=at,
        recorded_at=at,
        recorded_by_id=actor.id,
        idempotency_key=key or str(uuid.uuid4()),
        idempotency_fingerprint="0" * 64,
        status="confirmed",
    )
    db.add(p)
    db.flush()
    return p


def _add_allocation(db, payment, delivery, amount):
    a = PaymentAllocation(
        payment_id=payment.id,
        delivery_id=delivery.id,
        amount=Decimal(amount),
    )
    db.add(a)
    db.flush()
    return a


# ---------------------------------------------------------------------------
# Contract and access
# ---------------------------------------------------------------------------


def test_dashboard_requires_auth(client):
    r = client.get("/dashboard/summary")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_clerk_can_read_dashboard(client, clerk):
    r = client.get("/dashboard/summary", headers=_auth_header(clerk))
    assert r.status_code == 200, r.text


def test_period_out_of_range_422(client, admin):
    for days in (0, -1, 731):
        r = client.get(f"/dashboard/summary?days={days}", headers=_auth_header(admin))
        assert r.status_code == 422, f"days={days} returned {r.status_code}"


def test_response_shape(client, admin):
    r = client.get("/dashboard/summary", headers=_auth_header(admin))
    assert r.status_code == 200
    body = r.json()

    assert set(body) == {
        "generated_at",
        "period_days",
        "currency",
        "farmers_total",
        "farmers_by_status",
        "deliveries_in_period",
        "deliveries_value_in_period",
        "payments_in_period",
        "payments_value_in_period",
        "deductions_in_period",
        "deductions_value_in_period",
        "outstanding_debt_total",
        "available_credit_total",
        "deductions_total",
        "net_payable_total",
        "pending_valuation_count",
        "deliveries_by_line",
        "deliveries_daily",
        "recent_activity",
    }
    # Money crosses the wire as a string, never a float (D-010).
    assert isinstance(body["outstanding_debt_total"], str)
    assert isinstance(body["available_credit_total"], str)
    assert isinstance(body["deductions_total"], str)
    assert isinstance(body["net_payable_total"], str)
    assert body["period_days"] == 30
    assert set(body["farmers_by_status"]) == {
        "pending_verification",
        "active",
        "suspended",
        "archived",
        "merged",
    }


# ---------------------------------------------------------------------------
# Arithmetic: dashboard totals == sum of per-farmer balance
# ---------------------------------------------------------------------------


def test_totals_equal_sum_of_farmer_balances(client, admin, farmer, produce_line, db):
    now = datetime.now(UTC)

    other = Farmer(
        first_name="Second",
        last_name="Farmer",
        phone=f"+2547{uuid.uuid4().int % 10**8:08d}",
        status=FarmerStatus.ACTIVE.value,
        created_by_id=admin.id,
    )
    db.add(other)
    db.flush()

    # Farmer 1: one delivery, fully settled by an allocated payment.
    d1 = _add_delivery(
        db, farmer, produce_line, admin, quantity="100", rate="50", at=now
    )
    p1 = _add_payment(db, farmer, admin, amount="2000", at=now)
    _add_allocation(db, p1, d1, "2000")

    # Farmer 2: an older delivery plus an unallocated advance (credit).
    _add_delivery(
        db,
        other,
        produce_line,
        admin,
        quantity="40",
        rate="50",
        at=now - timedelta(days=60),
    )
    _add_payment(db, other, admin, amount="500", at=now - timedelta(days=60))

    r = client.get("/dashboard/summary", headers=_auth_header(admin))
    assert r.status_code == 200, r.text
    body = r.json()

    expected_debt = Decimal("0")
    expected_credit = Decimal("0")
    expected_pending = 0
    for f in (farmer, other):
        bal = ledger_service.compute_balance(db, f.id)
        expected_debt += bal.outstanding_debt
        expected_credit += bal.available_credit
        expected_pending += bal.pending_valuation_deliveries

    assert Decimal(body["outstanding_debt_total"]) == expected_debt
    assert Decimal(body["available_credit_total"]) == expected_credit
    assert body["pending_valuation_count"] == expected_pending

    # And the concrete numbers, so a formula change cannot pass silently.
    # Farmer 1: 5000 delivered - 2000 allocated = 3000.
    # Farmer 2: 2000 delivered, nothing allocated    = 2000.
    assert expected_debt == Decimal("5000")
    # 2500 received - 2000 allocated = 500 on account.
    assert expected_credit == Decimal("500")


def test_period_window_excludes_old_activity(client, admin, farmer, produce_line, db):
    now = datetime.now(UTC)
    _add_delivery(db, farmer, produce_line, admin, quantity="10", rate="50", at=now)
    _add_delivery(
        db,
        farmer,
        produce_line,
        admin,
        quantity="20",
        rate="50",
        at=now - timedelta(days=90),
    )

    body = client.get("/dashboard/summary?days=30", headers=_auth_header(admin)).json()

    # Only today's delivery is in the period...
    assert body["deliveries_in_period"] == 1
    assert Decimal(body["deliveries_value_in_period"]) == Decimal("500")
    # ...but both are part of the outstanding balance.
    assert Decimal(body["outstanding_debt_total"]) == Decimal("1500")

    # The daily series is zero-filled across the whole window.
    daily = body["deliveries_daily"]
    assert len(daily) == 30
    assert sum(bucket["count"] for bucket in daily) == 1
    assert daily[-1]["count"] == 1


def test_by_line_and_activity(client, admin, farmer, produce_line, db):
    now = datetime.now(UTC)
    _add_delivery(db, farmer, produce_line, admin, quantity="100", rate="50", at=now)
    _add_payment(db, farmer, admin, amount="1000", at=now)

    body = client.get("/dashboard/summary", headers=_auth_header(admin)).json()

    lines = body["deliveries_by_line"]
    assert len(lines) == 1
    assert lines[0]["produce_line_id"] == str(produce_line.id)
    assert lines[0]["produce_line_name"] == "Coffee"
    assert lines[0]["count"] == 1
    assert Decimal(lines[0]["value"]) == Decimal("5000")
    assert Decimal(lines[0]["quantity"]) == Decimal("100")

    activity = body["recent_activity"]
    assert len(activity) == 2
    kinds = {item["type"] for item in activity}
    assert kinds == {"delivery", "payment"}
    for item in activity:
        assert item["farmer_name"] == "Test Farmer"
        assert item["farmer_id"] == str(farmer.id)
        assert item["description"]
        assert isinstance(item["amount"], str)
