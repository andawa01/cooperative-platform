"""
Member bank details (D-036).

The bank rail's destination lives on the member. These hold the record to its
contract: both fields or neither, digits only, editable later, clearable.
A member with half an address is exactly the row a bank file would pay to
nowhere, so the pair is enforced in the schema, the service and the database.
"""

import uuid

from app.core.security import create_access_token


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides) -> dict:
    payload = {
        "first_name": "Bank",
        "last_name": "Member",
        "phone": f"07{uuid.uuid4().int % 10**8:08d}",
    }
    payload.update(overrides)
    return payload


def test_bank_details_are_saved_with_the_member(client, admin):
    r = client.post(
        "/farmers",
        json=_payload(bank_name="KCB", bank_account_number="0123456789"),
        headers=_auth(admin),
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["bank_name"] == "KCB"
    # Leading zeros survive: an account number is not an integer.
    assert body["bank_account_number"] == "0123456789"


def test_bank_details_must_be_a_pair(client, admin):
    r = client.post("/farmers", json=_payload(bank_name="KCB"), headers=_auth(admin))

    assert r.status_code == 422


def test_account_number_must_be_digits(client, admin):
    r = client.post(
        "/farmers",
        json=_payload(bank_name="KCB", bank_account_number="12AB567"),
        headers=_auth(admin),
    )

    assert r.status_code == 422


def test_bank_details_can_be_added_changed_and_cleared(client, admin):
    created = client.post("/farmers", json=_payload(), headers=_auth(admin))
    assert created.status_code == 201, created.text
    farmer_id = created.json()["id"]
    assert created.json()["bank_name"] is None

    added = client.patch(
        f"/farmers/{farmer_id}",
        json={"bank_name": "Equity", "bank_account_number": "1234567890"},
        headers=_auth(admin),
    )
    assert added.status_code == 200, added.text
    assert added.json()["bank_account_number"] == "1234567890"

    # Clearing one half would leave a destination the bank cannot credit, so
    # the resulting row is checked, not just the payload.
    half = client.patch(
        f"/farmers/{farmer_id}",
        json={"bank_name": None, "bank_account_number": "9999999999"},
        headers=_auth(admin),
    )
    assert half.status_code == 422

    still_there = client.get(f"/farmers/{farmer_id}", headers=_auth(admin))
    assert still_there.json()["bank_name"] == "Equity"

    cleared = client.patch(
        f"/farmers/{farmer_id}",
        json={"bank_name": None, "bank_account_number": None},
        headers=_auth(admin),
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["bank_name"] is None
    assert cleared.json()["bank_account_number"] is None
