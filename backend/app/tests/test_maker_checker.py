"""
Maker-checker on money writes (D-038).

What these hold the implementation to:

- A large reversal or dispatch is refused, not silently queued. The refusal
  says why and carries the header the UI keys on.
- Nothing moves until a *different* admin approves. Two people, enforced by
  the service and by a database CHECK.
- Approval executes through the same service as the direct path, with the
  approver as the actor, so the audit trail names whoever released the money.
- A request whose subject was corrected (or reversed) while it waited is
  rejected as no longer applicable, never paid twice.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole
from app.services import payment as payment_service

THRESHOLD = Decimal("20000")


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin2(db) -> User:
    u = User(
        email=f"admin2-{uuid.uuid4().hex[:8]}@test.io",
        full_name="Second Admin",
        hashed_password=hash_password("password-123"),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


def _pay(client, user, farmer, amount: str = "25000") -> dict:
    r = client.post(
        "/payments",
        json={
            "farmer_id": str(farmer.id),
            "amount": amount,
            "currency": "KES",
            "method": "cash",
            "paid_at": datetime.now(UTC).isoformat(),
            "idempotency_key": f"mc-{uuid.uuid4().hex[:16]}",
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _request(client, user, action: str, entity_id: str, reason: str = "large"):
    return client.post(
        "/approvals",
        json={"action": action, "entity_id": entity_id, "reason": reason},
        headers=_auth(user),
    )


def _reversal_count(client, user, farmer) -> int:
    r = client.get(
        "/payments",
        params={"farmer_id": str(farmer.id), "include_reversals": "true"},
        headers=_auth(user),
    )
    assert r.status_code == 200, r.text
    return r.json()["total"]


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_a_small_reversal_still_happens_immediately(client, admin, farmer):
    payment = _pay(client, admin, farmer, amount="500")

    r = client.post(
        f"/payments/{payment['id']}/reverse",
        json={"reason": "wrong member"},
        headers=_auth(admin),
    )

    assert r.status_code == 201, r.text


def test_a_large_reversal_is_refused_and_says_why(client, admin, farmer):
    payment = _pay(client, admin, farmer)

    r = client.post(
        f"/payments/{payment['id']}/reverse",
        json={"reason": "wrong member"},
        headers=_auth(admin),
    )

    assert r.status_code == 409
    assert r.headers["x-approval-required"] == "true"
    detail = r.json()["detail"]
    assert "maker-checker" in detail
    assert "different admin" in detail
    # Refused means refused: no reversal row was written.
    assert _reversal_count(client, admin, farmer) == 1


def test_a_large_deduction_reversal_is_gated(client, admin, farmer):
    created = client.post(
        "/deductions",
        json={
            "farmer_id": str(farmer.id),
            "amount": "25000",
            "currency": "KES",
            "reason_code": "loan_recovery",
            "applied_at": datetime.now(UTC).date().isoformat(),
        },
        headers=_auth(admin),
    )
    assert created.status_code == 201, created.text
    deduction = created.json()

    r = client.post(
        f"/deductions/{deduction['id']}/reverse",
        json={"reason": "mistake"},
        headers=_auth(admin),
    )

    assert r.status_code == 409
    assert r.headers["x-approval-required"] == "true"


def test_a_dispatch_above_the_limit_needs_approval(
    client, admin, admin2, farmer, produce_line, rate
):
    delivered = client.post(
        "/deliveries",
        json={
            "farmer_id": str(farmer.id),
            "produce_line_id": str(produce_line.id),
            "quantity": "500",
            "delivered_at": datetime.now(UTC).isoformat(),
        },
        headers=_auth(admin),
    )
    assert delivered.status_code == 201, delivered.text
    delivery = delivered.json()
    if delivery["rate_snapshot"] is None:
        valued = client.post(
            f"/deliveries/{delivery['id']}/value", headers=_auth(admin)
        )
        assert valued.status_code < 300, valued.text

    run = client.post(
        "/payout-runs", json={"method": "cash"}, headers=_auth(admin)
    ).json()
    assert Decimal(run["total_amount"]) == Decimal("25000")
    approved_run = client.post(
        f"/payout-runs/{run['id']}/approve", headers=_auth(admin)
    )
    assert approved_run.status_code == 200, approved_run.text

    refused = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))
    assert refused.status_code == 409
    assert refused.headers["x-approval-required"] == "true"

    requested = _request(client, admin, "payout.dispatch", run["id"])
    assert requested.status_code == 201, requested.text
    approval = requested.json()
    assert approval["summary"].startswith("Dispatch RUN-")
    assert Decimal(approval["amount"]) == Decimal("25000")

    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"note": "checked the run"},
        headers=_auth(admin2),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"

    after = client.get(f"/payout-runs/{run['id']}", headers=_auth(admin))
    assert after.json()["status"] == "dispatched"
    assert after.json()["paid_count"] == 1


# ---------------------------------------------------------------------------
# Request + approve
# ---------------------------------------------------------------------------


def test_approval_by_a_second_admin_executes_the_reversal(
    client, admin, admin2, farmer, db
):
    payment = _pay(client, admin, farmer)

    requested = _request(
        client, admin, "payment.reverse", payment["id"], reason="duplicate payment"
    )
    assert requested.status_code == 201, requested.text
    approval = requested.json()
    assert approval["status"] == "pending"
    assert approval["requested_by_name"] == "Test Admin"
    assert Decimal(approval["amount"]) == Decimal("25000")

    approved = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"note": "confirmed with the treasurer"},
        headers=_auth(admin2),
    )

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["decided_by_name"] == "Second Admin"
    assert _reversal_count(client, admin, farmer) == 2

    # The reversal's actor is the approver, not the requester: the trail must
    # name whoever released the money.
    reversals = client.get(
        "/payments",
        params={"farmer_id": str(farmer.id), "include_reversals": "true"},
        headers=_auth(admin),
    ).json()["items"]
    reversal = [p for p in reversals if p["reversal_of_id"] is not None][0]
    assert reversal["recorded_by_id"] == str(admin2.id)


def test_one_admin_cannot_approve_their_own_request(client, admin, farmer):
    payment = _pay(client, admin, farmer)
    approval = _request(client, admin, "payment.reverse", payment["id"]).json()

    r = client.post(
        f"/approvals/{approval['id']}/approve", json={}, headers=_auth(admin)
    )

    assert r.status_code == 409
    assert "different admin" in r.json()["detail"]
    assert _reversal_count(client, admin, farmer) == 1


def test_rejecting_leaves_the_money_alone(client, admin, admin2, farmer):
    payment = _pay(client, admin, farmer)
    approval = _request(client, admin, "payment.reverse", payment["id"]).json()

    r = client.post(
        f"/approvals/{approval['id']}/reject",
        json={"note": "the payment was correct"},
        headers=_auth(admin2),
    )

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"
    assert r.json()["decision_note"] == "the payment was correct"
    assert _reversal_count(client, admin, farmer) == 1


def test_asking_twice_returns_the_same_pending_request(client, admin, farmer):
    payment = _pay(client, admin, farmer)

    first = _request(client, admin, "payment.reverse", payment["id"])
    second = _request(client, admin, "payment.reverse", payment["id"])

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    queue = client.get(
        "/approvals", params={"status": "pending"}, headers=_auth(admin)
    ).json()
    assert queue["total"] == 1


def test_a_subject_cannot_be_decided_twice(client, admin, admin2, farmer):
    payment = _pay(client, admin, farmer)
    approval = _request(client, admin, "payment.reverse", payment["id"]).json()

    first = client.post(
        f"/approvals/{approval['id']}/approve", json={}, headers=_auth(admin2)
    )
    assert first.status_code == 200

    second = client.post(
        f"/approvals/{approval['id']}/reject", json={}, headers=_auth(admin2)
    )
    assert second.status_code == 409
    assert "already approved" in second.json()["detail"]


def test_an_approval_whose_subject_moved_is_rejected_as_stale(
    client, admin, admin2, farmer, db
):
    """The payment was corrected directly while the request waited."""
    payment = _pay(client, admin, farmer)
    approval = _request(client, admin, "payment.reverse", payment["id"]).json()

    payment_service.reverse_payment(
        db, uuid.UUID(payment["id"]), "fixed directly", admin
    )

    r = client.post(
        f"/approvals/{approval['id']}/approve", json={}, headers=_auth(admin2)
    )

    assert r.status_code == 409
    assert "already reversed" in r.json()["detail"]

    queue = client.get(
        "/approvals", params={"status": "rejected"}, headers=_auth(admin)
    ).json()
    assert queue["total"] == 1
    assert "No longer applicable" in queue["items"][0]["decision_note"]


def test_a_request_below_the_limit_is_refused(client, admin, farmer):
    payment = _pay(client, admin, farmer, amount="500")

    r = _request(client, admin, "payment.reverse", payment["id"])

    assert r.status_code == 409
    assert "below" in r.json()["detail"]


def test_the_queue_is_admin_only(client, admin, clerk, farmer):
    payment = _pay(client, admin, farmer)

    assert client.get("/approvals", headers=_auth(clerk)).status_code == 403
    assert _request(client, clerk, "payment.reverse", payment["id"]).status_code == 403
