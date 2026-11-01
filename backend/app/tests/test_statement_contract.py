"""
Statement endpoint contract.

This file exists because of a bug: the response schema declared `from_`/`to`
while the service constructed it with `start=`/`end=`, so pydantic rejected the
payload and the endpoint answered 500 on every call. Nothing caught it, because
the statement was only exercised through the service in other tests, never over
HTTP.

The assertions here are deliberately about the wire shape — the client reads
`start`, `end`, `opening`, `entries` and `closing`, so those names are part of
the contract, not an implementation detail.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest


def _login(client, email: str, password: str = "password-123") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def clerk_token(client, clerk) -> str:
    return _login(client, clerk.email)


def _record_delivery(client, token: str, farmer, produce_line, quantity="10.0000"):
    r = client.post(
        "/deliveries",
        headers=_auth(token),
        json={
            "farmer_id": str(farmer.id),
            "produce_line_id": str(produce_line.id),
            "quantity": quantity,
            "delivered_at": "2025-06-15T10:00:00Z",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_statement_responds_with_the_documented_field_names(
    client, clerk_token, farmer, produce_line, rate
):
    _record_delivery(client, clerk_token, farmer, produce_line)

    r = client.get(
        f"/farmers/{farmer.id}/statement",
        headers=_auth(clerk_token),
        params={"start": "2025-01-01", "end": "2025-12-31"},
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["farmer_id"] == str(farmer.id)
    assert body["start"].startswith("2025-01-01")
    assert body["end"].startswith("2025-12-31")
    assert body["currency"] == "KES"
    assert set(body["opening"]) == {"outstanding_debt", "available_credit"}
    assert set(body["closing"]) == {"outstanding_debt", "available_credit"}
    assert isinstance(body["entries"], list)
    assert len(body["entries"]) == 1

    entry = body["entries"][0]
    assert entry["type"] == "delivery"
    assert set(entry) >= {
        "date",
        "type",
        "amount",
        "description",
        "debt_after",
        "credit_after",
    }


def test_statement_closing_matches_the_balance_endpoint(
    client, clerk_token, farmer, produce_line, rate
):
    """The two endpoints must never disagree about the same position."""
    _record_delivery(client, clerk_token, farmer, produce_line)

    today = datetime.now(UTC).date()
    r = client.get(
        f"/farmers/{farmer.id}/statement",
        headers=_auth(clerk_token),
        params={
            "start": (today - timedelta(days=365)).isoformat(),
            "end": today.isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    closing = r.json()["closing"]

    balance = client.get(
        f"/farmers/{farmer.id}/balance", headers=_auth(clerk_token)
    ).json()
    assert closing["outstanding_debt"] == balance["outstanding_debt"]
    assert closing["available_credit"] == balance["available_credit"]


def test_statement_rejects_an_inverted_range(client, clerk_token, farmer):
    r = client.get(
        f"/farmers/{farmer.id}/statement",
        headers=_auth(clerk_token),
        params={"start": "2025-12-31", "end": "2025-01-01"},
    )
    assert r.status_code == 422


def test_statement_requires_authentication(client, farmer):
    assert client.get(f"/farmers/{farmer.id}/statement").status_code == 401


def test_unknown_farmer_is_404(client, clerk_token):
    r = client.get(
        f"/farmers/{uuid.uuid4()}/statement", headers=_auth(clerk_token)
    )
    assert r.status_code == 404
