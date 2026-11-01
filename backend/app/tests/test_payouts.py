"""
Payout runs.

What these tests hold the implementation to:

- A run snapshots what each member was owed *at creation*; a delivery or
  deduction recorded afterwards does not change an amount already promised.
- A run is not a ledger entry. Only the `Payment` each item produces moves the
  balance, so nothing is counted twice.
- Dispatching twice pays once — the idempotency key is derived from the item,
  not from the request.
- A clerk cannot release money; they can read a run so the counter can answer
  "have I been paid?".
"""

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit import AuditLog
from app.models.farmer import Farmer, FarmerStatus


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _deliver(client, user, farmer, produce_line, quantity: str = "10") -> dict:
    """Record a delivery and make sure it is valued, returning the row."""
    r = client.post(
        "/deliveries",
        json={
            "farmer_id": str(farmer.id),
            "produce_line_id": str(produce_line.id),
            "quantity": quantity,
            "delivered_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    delivery = r.json()
    if delivery["rate_snapshot"] is None:
        valued = client.post(f"/deliveries/{delivery['id']}/value", headers=_auth(user))
        assert valued.status_code < 300, valued.text
        delivery = valued.json()
    return delivery


def _create_run(client, user, **overrides):
    payload: dict = {"method": "mobile_money"}
    payload.update(overrides)
    return client.post("/payout-runs", json=payload, headers=_auth(user))


# ---------------------------------------------------------------------------
# Creation: the snapshot
# ---------------------------------------------------------------------------


def test_run_snapshots_each_members_payable(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)  # 10 kg @ 50 = 500

    r = _create_run(client, admin, notes="October settlement")

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["reference"].startswith("RUN-")
    assert body["method"] == "mobile_money"
    assert body["notes"] == "October settlement"
    assert body["item_count"] == 1
    assert Decimal(body["total_amount"]) == Decimal("500")
    assert body["paid_count"] == 0

    item = body["items"][0]
    assert item["farmer_id"] == str(farmer.id)
    assert item["farmer_name"] == farmer.full_name
    assert item["phone"] == farmer.phone
    assert Decimal(item["amount"]) == Decimal("500")
    assert item["status"] == "pending"
    assert item["payment_id"] is None


def test_a_run_with_nothing_payable_is_refused(client, admin, farmer):
    """An empty run is a file that pays nobody — better to fail than to leave it."""
    r = _create_run(client, admin)

    assert r.status_code == 409
    assert "nothing to pay" in r.json()["detail"]


def test_a_member_can_be_excluded_by_naming_the_others(
    client, db, admin, clerk, farmer, produce_line, rate
):
    _deliver(client, admin, farmer, produce_line)

    other = Farmer(
        first_name="Second",
        last_name="Member",
        phone="+254700000042",
        status=FarmerStatus.ACTIVE.value,
        created_by_id=clerk.id,
    )
    db.add(other)
    db.flush()
    _deliver(client, admin, other, produce_line)

    r = _create_run(client, admin, farmer_ids=[str(farmer.id)])

    assert r.status_code == 201, r.text
    assert r.json()["item_count"] == 1
    assert r.json()["items"][0]["farmer_id"] == str(farmer.id)


def test_amounts_are_frozen_at_creation(client, admin, farmer, produce_line, rate):
    """
    A promise made on Thursday must not shrink because of a Friday correction.
    """
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()

    # A second delivery arrives after the run exists.
    _deliver(client, admin, farmer, produce_line, quantity="20")

    after = client.get(f"/payout-runs/{run['id']}", headers=_auth(admin)).json()
    balance = client.get(f"/farmers/{farmer.id}/balance", headers=_auth(admin)).json()

    assert Decimal(after["total_amount"]) == Decimal("500")
    assert Decimal(balance["net_payable"]) == Decimal("1500")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_clerk_cannot_release_money(client, admin, clerk, farmer, produce_line, rate):
    """A run releases money for the whole co-op; that is not a clerk's call."""
    _deliver(client, admin, farmer, produce_line)

    assert _create_run(client, clerk).status_code == 403

    # An admin builds the run; the clerk still cannot move it along.
    run = _create_run(client, admin).json()
    for action in ("approve", "dispatch", "cancel"):
        blocked = client.post(
            f"/payout-runs/{run['id']}/{action}", headers=_auth(clerk)
        )
        assert blocked.status_code == 403, action


def test_clerk_can_read_a_run(client, db, admin, clerk, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()

    assert client.get("/payout-runs", headers=_auth(clerk)).status_code == 200
    assert (
        client.get(f"/payout-runs/{run['id']}", headers=_auth(clerk)).status_code == 200
    )


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_approve_then_dispatch_pays_the_member(
    client, admin, farmer, produce_line, rate
):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()

    approved = client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(admin))
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_by_id"] == str(admin.id)

    dispatched = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))
    assert dispatched.status_code == 200, dispatched.text
    result = dispatched.json()
    assert result["paid"] == 1
    assert result["failed"] == 0
    assert result["batch"]["status"] == "dispatched"
    assert result["batch"]["paid_count"] == 1

    balance = client.get(f"/farmers/{farmer.id}/balance", headers=_auth(admin)).json()
    assert Decimal(balance["net_payable"]) == Decimal("0")

    payments = client.get(
        "/payments", params={"farmer_id": str(farmer.id)}, headers=_auth(admin)
    ).json()
    assert payments["total"] == 1
    payment = payments["items"][0]
    assert Decimal(payment["amount"]) == Decimal("500")
    assert payment["reference"] == run["reference"]
    assert payment["method"] == "mobile_money"


def test_dispatch_requires_approval(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()

    r = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))

    assert r.status_code == 409
    assert "Approve the run" in r.json()["detail"]


def test_a_run_cannot_be_approved_twice(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()
    client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(admin))

    again = client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(admin))

    assert again.status_code == 409


def test_dispatching_twice_pays_once(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()
    client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(admin))

    first = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))
    second = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))

    assert first.json()["paid"] == 1
    assert second.status_code == 200
    assert second.json()["paid"] == 0

    payments = client.get(
        "/payments", params={"farmer_id": str(farmer.id)}, headers=_auth(admin)
    ).json()
    assert payments["total"] == 1, "a second dispatch must not pay the member again"


def test_cancel_stops_a_run_from_paying(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()

    cancelled = client.post(f"/payout-runs/{run['id']}/cancel", headers=_auth(admin))
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    blocked = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))
    assert blocked.status_code == 409


def test_a_dispatched_run_cannot_be_cancelled(
    client, admin, farmer, produce_line, rate
):
    """Cancelling after money moved would imply the payment was withdrawn."""
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()
    client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(admin))
    client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))

    r = client.post(f"/payout-runs/{run['id']}/cancel", headers=_auth(admin))

    assert r.status_code == 409
    assert "reverse the payments" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Money that already exists: deductions reduce what a run pays
# ---------------------------------------------------------------------------


def test_a_run_pays_net_of_deductions(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)  # 500 earned
    deduction = client.post(
        "/deductions",
        json={
            "farmer_id": str(farmer.id),
            "amount": "120.0000",
            "currency": "KES",
            "reason_code": "transport",
            "applied_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(admin),
    )
    assert deduction.status_code == 201, deduction.text

    run = _create_run(client, admin).json()

    assert Decimal(run["total_amount"]) == Decimal("380")


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------


def test_list_reports_totals_without_a_query_per_row(
    client, admin, farmer, produce_line, rate
):
    _deliver(client, admin, farmer, produce_line)
    _create_run(client, admin)

    r = client.get("/payout-runs", headers=_auth(admin))

    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert body["items"][0]["item_count"] == 1
    assert Decimal(body["items"][0]["total_amount"]) == Decimal("500")


def test_export_is_a_disbursement_file(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()

    r = client.get(f"/payout-runs/{run['id']}/export", headers=_auth(admin))

    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8").lstrip("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    assert len(rows) == 1
    assert rows[0]["reference"] == run["reference"]
    assert rows[0]["farmer"] == farmer.full_name
    # A mobile-money file needs the destination, not just the name.
    assert rows[0]["phone"] == farmer.phone
    assert rows[0]["amount"] == "500.0000"
    assert rows[0]["status"] == "pending"


def test_run_actions_are_audited(client, db, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _create_run(client, admin).json()
    client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(admin))
    client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))

    actions = list(
        db.scalars(
            select(AuditLog.action).where(AuditLog.entity_id == uuid.UUID(run["id"]))
        )
    )

    assert sorted(actions) == [
        "payout.approve",
        "payout.create",
        "payout.dispatch",
    ]
