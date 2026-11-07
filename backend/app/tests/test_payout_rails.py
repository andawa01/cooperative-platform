"""
Payout rails — the disbursement file (backlog 1.3).

What these hold the implementation to:

- The M-Pesa file is a bulk upload, not a report: one row per unpaid member,
  in the portal's column order, with a destination the portal can dial.
- A member who already has a payment is never in the file. Paying twice is the
  one failure a payout file must make impossible.
- Methods that cannot produce a file say so, with a reason a treasurer can act
  on, instead of emitting a file that will bounce at the bank.
"""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal

from app.core.security import create_access_token


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _deliver(client, user, farmer, produce_line, quantity: str = "10") -> dict:
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


def _run(client, user, method: str = "mobile_money", approve: bool = True) -> dict:
    created = client.post("/payout-runs", json={"method": method}, headers=_auth(user))
    assert created.status_code == 201, created.text
    run = created.json()
    if approve:
        approved = client.post(f"/payout-runs/{run['id']}/approve", headers=_auth(user))
        assert approved.status_code == 200, approved.text
        run = approved.json()
    return run


def _rows(response) -> list[dict]:
    text = response.content.decode("utf-8")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def test_mpesa_file_is_a_bulk_upload(client, admin, farmer, produce_line, rate):
    """10 kg @ 50 = 500, paid to the farmer's M-Pesa number."""
    _deliver(client, admin, farmer, produce_line)
    run = _run(client, admin)

    r = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))

    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["x-payout-rows"] == "1"
    disposition = r.headers["content-disposition"]
    assert f"mpesa-b2c-{run['reference']}" in disposition.replace("\\", "-")
    # A portal reads this file; a BOM would corrupt the first column name.
    assert not r.content.startswith(b"\xef\xbb\xbf")

    rows = _rows(r)
    assert len(rows) == 1
    row = rows[0]
    assert row["CommandID"] == "BusinessPayment"
    assert row["UniqueName"] == run["reference"].replace("-", "")
    assert row["Amount"] == "500.00"
    assert row["MSISDN"] == farmer.phone.lstrip("+")
    assert run["reference"] in row["Remarks"]
    assert row["Occasion"] == run["reference"]


def test_a_paid_member_is_not_in_the_file(client, admin, farmer, produce_line, rate):
    """
    The file is an instruction to pay, so a member who has already been paid
    must not appear in it — a second upload would pay them twice.
    """
    _deliver(client, admin, farmer, produce_line)
    run = _run(client, admin)

    before = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))
    assert len(_rows(before)) == 1

    dispatched = client.post(f"/payout-runs/{run['id']}/dispatch", headers=_auth(admin))
    assert dispatched.status_code == 200, dispatched.text

    after = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))
    assert after.status_code == 409
    assert "already has a payment" in after.json()["detail"]


def test_cash_run_has_no_file(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _run(client, admin, method="cash")

    r = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))

    assert r.status_code == 409
    assert "across the counter" in r.json()["detail"]


def test_bank_run_says_what_is_missing(client, admin, farmer, produce_line, rate):
    """No account numbers on members means no file — say so, do not guess."""
    _deliver(client, admin, farmer, produce_line)
    run = _run(client, admin, method="bank_transfer")

    r = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))

    assert r.status_code == 409
    assert "account number" in r.json()["detail"]


def test_a_cancelled_run_produces_no_file(client, admin, farmer, produce_line, rate):
    _deliver(client, admin, farmer, produce_line)
    run = _run(client, admin)
    client.post(f"/payout-runs/{run['id']}/cancel", headers=_auth(admin))

    r = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))

    assert r.status_code == 409
    assert "cancelled" in r.json()["detail"]


def test_clerk_can_download_the_file(client, admin, clerk, farmer, produce_line, rate):
    """The counter answers "have I been paid?" and can print the schedule."""
    _deliver(client, admin, farmer, produce_line)
    run = _run(client, admin)

    r = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(clerk))

    assert r.status_code == 200, r.text


def test_unknown_run_is_not_found(client, admin):
    r = client.get(
        "/payout-runs/00000000-0000-0000-0000-000000000000/rail-file",
        headers=_auth(admin),
    )

    assert r.status_code == 404


def test_amounts_are_paid_in_minor_units(client, admin, farmer, produce_line, rate):
    """
    The ledger keeps four decimals; a portal pays to the cent. The file carries
    the amount that can actually be credited.
    """
    _deliver(client, admin, farmer, produce_line, quantity="10.333")
    run = _run(client, admin)

    r = client.get(f"/payout-runs/{run['id']}/rail-file", headers=_auth(admin))

    rows = _rows(r)
    assert Decimal(rows[0]["Amount"]) == Decimal(run["items"][0]["amount"]).quantize(
        Decimal("0.01")
    )
    assert rows[0]["Amount"].count(".") == 1
    assert len(rows[0]["Amount"].split(".")[1]) == 2
