"""
Deductions: the third ledger direction.

What these tests pin down:

- A deduction withholds from the settlement but does not change the debt or
  the credit — it moves `net_payable` and nothing else.
- Reversal is a compensating negative row, one per original, and only an
  admin may write one.
- The closing figures on a statement still equal /farmers/{id}/balance once
  deductions exist. That is the invariant the whole ledger rests on, and it
  is exactly what would break if deductions were folded into debt.
"""

import csv
import io
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.audit import AuditLog


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _record(client, user, farmer, **overrides):
    payload = {
        "farmer_id": str(farmer.id),
        "amount": "250.0000",
        "currency": "KES",
        "reason_code": "transport",
        "applied_at": datetime.now(UTC).isoformat(),
    }
    payload.update(overrides)
    return client.post("/deductions", json=payload, headers=_auth(user))


def _csv_rows(response) -> list[dict]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8").lstrip("\ufeff")
    return list(csv.DictReader(io.StringIO(text, newline="")))


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


def test_clerk_records_a_deduction(client, db, clerk, farmer):
    r = _record(client, clerk, farmer)

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["farmer_id"] == str(farmer.id)
    assert body["farmer_name"] == farmer.full_name
    assert body["reason_code"] == "transport"
    assert body["reference"] is None
    assert body["reversal_of_id"] is None
    assert body["recorded_by_id"] == str(clerk.id)


def test_reason_code_is_a_closed_set(client, clerk, farmer):
    r = _record(client, clerk, farmer, reason_code="bribe")

    assert r.status_code == 422


def test_amount_must_be_positive(client, clerk, farmer):
    r = _record(client, clerk, farmer, amount="-250.0000")

    assert r.status_code == 422


def test_unknown_farmer_is_404(client, clerk):
    r = _record(client, clerk, farmer=type("F", (), {"id": uuid.uuid4()})())

    assert r.status_code == 404
    assert r.json()["detail"] == "Farmer not found"


def test_recording_requires_a_token(client, farmer):
    r = client.post(
        "/deductions",
        json={
            "farmer_id": str(farmer.id),
            "amount": "10.0000",
            "currency": "KES",
            "reason_code": "cess",
            "applied_at": datetime.now(UTC).isoformat(),
        },
    )

    assert r.status_code == 401


def test_recording_writes_an_audit_row(client, db, clerk, farmer):
    r = _record(client, clerk, farmer, reference="TRP-4417")
    assert r.status_code == 201, r.text

    actions = list(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_id == uuid.UUID(r.json()["id"])
            )
        )
    )
    assert actions == ["deduction.create"]


# ---------------------------------------------------------------------------
# Reversal
# ---------------------------------------------------------------------------


def test_clerk_cannot_reverse(client, clerk, farmer):
    original = _record(client, clerk, farmer).json()

    r = client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "charged twice"},
        headers=_auth(clerk),
    )

    assert r.status_code == 403


def test_admin_reversal_inserts_a_negative_row(client, db, admin, clerk, farmer):
    original = _record(client, clerk, farmer).json()

    r = client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "charged twice"},
        headers=_auth(admin),
    )

    assert r.status_code == 201, r.text
    reversal = r.json()
    assert reversal["reversal_of_id"] == original["id"]
    assert float(reversal["amount"]) == -250.0
    assert reversal["reason_code"] == "transport"

    actions = sorted(
        db.scalars(
            select(AuditLog.action).where(
                AuditLog.entity_id == uuid.UUID(original["id"])
            )
        )
    )
    assert actions == ["deduction.create", "deduction.reverse"]


def test_a_deduction_can_only_be_reversed_once(client, admin, clerk, farmer):
    original = _record(client, clerk, farmer).json()
    first = client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "charged twice"},
        headers=_auth(admin),
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "again"},
        headers=_auth(admin),
    )

    assert second.status_code == 409
    assert second.json()["detail"] == "Deduction already reversed"


def test_a_reversal_cannot_itself_be_reversed(client, admin, clerk, farmer):
    original = _record(client, clerk, farmer).json()
    reversal = client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "charged twice"},
        headers=_auth(admin),
    ).json()

    r = client.post(
        f"/deductions/{reversal['id']}/reverse",
        json={"reason": "un-reverse"},
        headers=_auth(admin),
    )

    assert r.status_code == 409
    assert r.json()["detail"] == "Cannot reverse a reversal"


def test_reversing_an_unknown_deduction_is_404(client, admin):
    r = client.post(
        f"/deductions/{uuid.uuid4()}/reverse",
        json={"reason": "nope"},
        headers=_auth(admin),
    )

    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Effect on the balance: withheld, not owed
# ---------------------------------------------------------------------------


def test_balance_withholds_without_touching_debt_or_credit(client, clerk, farmer):
    assert _record(client, clerk, farmer, amount="250.0000").status_code == 201

    body = client.get(f"/farmers/{farmer.id}/balance", headers=_auth(clerk)).json()

    assert float(body["outstanding_debt"]) == 0.0
    assert float(body["available_credit"]) == 0.0
    assert float(body["deductions_total"]) == 250.0
    # Nothing was earned, so the member is 250 in arrears.
    assert float(body["net_payable"]) == -250.0


def test_reversal_restores_net_payable(client, admin, clerk, farmer):
    original = _record(client, clerk, farmer, amount="250.0000").json()
    client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "wrong farmer"},
        headers=_auth(admin),
    )

    body = client.get(f"/farmers/{farmer.id}/balance", headers=_auth(clerk)).json()

    assert float(body["deductions_total"]) == 0.0
    assert float(body["net_payable"]) == 0.0


def test_statement_closing_matches_balance(client, admin, clerk, farmer):
    _record(client, clerk, farmer, amount="120.0000")
    _record(
        client, clerk, farmer, amount="80.0000", reason_code="cess", reference="CESS-9"
    )

    statement = client.get(
        f"/farmers/{farmer.id}/statement", headers=_auth(admin)
    ).json()
    balance = client.get(f"/farmers/{farmer.id}/balance", headers=_auth(admin)).json()

    assert [e["type"] for e in statement["entries"]] == ["deduction", "deduction"]
    assert float(statement["closing"]["deductions_total"]) == 200.0
    assert float(statement["closing"]["net_payable"]) == float(balance["net_payable"])
    assert float(statement["closing"]["outstanding_debt"]) == float(
        balance["outstanding_debt"]
    )
    # Entries are shown signed: a charge reduces what the member receives.
    assert float(statement["entries"][0]["amount"]) == -120.0


def test_statement_keeps_a_reversal_in_the_period_it_corrects(
    client, admin, clerk, farmer
):
    original = _record(client, clerk, farmer, amount="300.0000").json()
    client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "keyed against the wrong member"},
        headers=_auth(admin),
    )

    statement = client.get(
        f"/farmers/{farmer.id}/statement", headers=_auth(admin)
    ).json()

    assert [e["type"] for e in statement["entries"]] == [
        "deduction",
        "deduction_reversal",
    ]
    assert statement["entries"][1]["reversal_of_id"] == original["id"]
    assert float(statement["closing"]["deductions_total"]) == 0.0


def test_dashboard_agrees_with_the_farmer_balance(client, clerk, farmer):
    """The cooperative total must equal the sum of what the ledger says."""
    _record(client, clerk, farmer, amount="90.0000")

    summary = client.get("/dashboard/summary", headers=_auth(clerk)).json()
    balance = client.get(f"/farmers/{farmer.id}/balance", headers=_auth(clerk)).json()

    assert float(summary["deductions_total"]) == float(balance["deductions_total"])
    assert float(summary["net_payable_total"]) == float(balance["net_payable"])
    assert summary["deductions_in_period"] == 1
    assert float(summary["deductions_value_in_period"]) == 90.0


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------


def test_list_hides_reversals_by_default(client, admin, clerk, farmer):
    original = _record(client, clerk, farmer).json()
    client.post(
        f"/deductions/{original['id']}/reverse",
        json={"reason": "correction"},
        headers=_auth(admin),
    )

    default = client.get("/deductions", headers=_auth(clerk)).json()
    with_reversals = client.get(
        "/deductions", params={"include_reversals": "true"}, headers=_auth(clerk)
    ).json()

    assert default["total"] == 1
    assert with_reversals["total"] == 2


def test_list_filters_by_farmer_and_reason(client, db, clerk, farmer, produce_line):
    from app.models.farmer import Farmer, FarmerStatus

    other = Farmer(
        first_name="Other",
        last_name="Member",
        phone="+254700000001",
        status=FarmerStatus.ACTIVE.value,
        created_by_id=clerk.id,
    )
    db.add(other)
    db.flush()

    _record(client, clerk, farmer, reason_code="transport")
    _record(client, clerk, farmer, reason_code="cess")
    _record(client, clerk, other, reason_code="transport")

    by_farmer = client.get(
        "/deductions", params={"farmer_id": str(farmer.id)}, headers=_auth(clerk)
    ).json()
    by_reason = client.get(
        "/deductions", params={"reason_code": "transport"}, headers=_auth(clerk)
    ).json()

    assert by_farmer["total"] == 2
    assert by_reason["total"] == 2
    assert {item["reason_code"] for item in by_reason["items"]} == {"transport"}


def test_export_matches_the_filter(client, clerk, farmer):
    _record(client, clerk, farmer, amount="40.0000", reference="TRP-1")
    _record(client, clerk, farmer, amount="15.5000", reason_code="cess")

    rows = _csv_rows(
        client.get(
            "/deductions/export", params={"reason_code": "cess"}, headers=_auth(clerk)
        )
    )

    assert len(rows) == 1
    assert rows[0]["reason_code"] == "cess"
    # Full precision, no thousands separators — a spreadsheet must be able to
    # SUM the column without cleaning it first.
    assert rows[0]["amount"] == "15.5000"
    assert rows[0]["kind"] == "deduction"
    assert rows[0]["farmer"] == farmer.full_name


def test_export_is_not_shadowed_by_the_id_route(client, clerk, farmer):
    """`/deductions/export` must not be parsed as a deduction id."""
    r = client.get("/deductions/export", headers=_auth(clerk))

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")


def test_get_one(client, clerk, farmer):
    original = _record(client, clerk, farmer).json()

    r = client.get(f"/deductions/{original['id']}", headers=_auth(clerk))

    assert r.status_code == 200
    assert r.json()["id"] == original["id"]
