"""
User administration and CSV export tests.

Both features sit on the permission boundary, so the properties under test are
about who is allowed to do what, and about the exports being the same data the
list screen showed rather than a second, subtly different query.

Scope note on the last-admin guard: through this API it is unreachable, because
the actor must themselves be an active admin, which means `other_admins >= 1`
whenever the check runs. It is kept as defence in depth for a future path that
deactivates an admin some other way, so it has no test here.
"""

import csv
import io
import uuid

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, email: str, password: str = "password-123") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _csv_rows(response) -> list[dict]:
    """Decode a CSV download, stripping the UTF-8 BOM Excel needs."""
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


@pytest.fixture
def admin_token(client, admin) -> str:
    return _login(client, admin.email)


@pytest.fixture
def clerk_token(client, clerk) -> str:
    return _login(client, clerk.email)


def _new_user(client, admin_token, role: str = "clerk") -> dict:
    email = f"managed-{uuid.uuid4().hex[:8]}@test.io"
    r = client.post(
        "/auth/register",
        headers=_auth(admin_token),
        json={
            "email": email,
            "full_name": "Managed User",
            "password": "a-long-enough-password",
            "role": role,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def test_user_list_is_admin_only(client, admin_token, clerk_token):
    assert client.get("/users").status_code == 401
    assert client.get("/users", headers=_auth(clerk_token)).status_code == 403
    assert client.get("/users", headers=_auth(admin_token)).status_code == 200


def test_user_patch_is_admin_only(client, clerk, clerk_token, admin_token):
    r = client.patch(
        f"/users/{clerk.id}",
        headers=_auth(clerk_token),
        json={"role": "admin"},
    )
    assert r.status_code == 403

    r = client.patch(
        f"/users/{clerk.id}",
        headers=_auth(admin_token),
        json={"role": "admin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"


def test_list_returns_accounts_and_never_a_password(client, admin_token, clerk):
    r = client.get("/users", headers=_auth(admin_token), params={"limit": 200})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 2
    assert str(clerk.id) in [item["id"] for item in body["items"]]

    for item in body["items"]:
        assert "hashed_password" not in item
        assert set(item) == {"id", "email", "full_name", "role", "is_active"}


def test_search_filters_by_name_or_email(client, admin_token):
    unique = uuid.uuid4().hex[:6]
    r = client.post(
        "/auth/register",
        headers=_auth(admin_token),
        json={
            "email": f"searchable-{unique}@test.io",
            "full_name": f"Searchable {unique}",
            "password": "a-long-enough-password",
            "role": "clerk",
        },
    )
    assert r.status_code == 201, r.text

    r = client.get("/users", headers=_auth(admin_token), params={"search": unique})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1


# ---------------------------------------------------------------------------
# Lockout guards
# ---------------------------------------------------------------------------


def test_admin_cannot_change_their_own_role(client, admin, admin_token):
    r = client.patch(
        f"/users/{admin.id}",
        headers=_auth(admin_token),
        json={"role": "clerk"},
    )
    assert r.status_code == 409
    assert "own role" in r.json()["detail"]

    # And the role really is unchanged.
    me = client.get("/auth/me", headers=_auth(admin_token))
    assert me.json()["role"] == "admin"


def test_admin_cannot_deactivate_themselves(client, admin, admin_token):
    r = client.patch(
        f"/users/{admin.id}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert r.status_code == 409
    assert client.get("/auth/me", headers=_auth(admin_token)).status_code == 200


def test_no_op_patch_writes_no_audit_entry(client, admin_token, clerk):
    """Re-sending the current values is not a change, so it is not an event."""
    for _ in range(2):
        r = client.patch(
            f"/users/{clerk.id}",
            headers=_auth(admin_token),
            json={"full_name": clerk.full_name},
        )
        assert r.status_code == 200, r.text

    entries = client.get(
        "/audit",
        headers=_auth(admin_token),
        params={"entity_type": "user", "entity_id": str(clerk.id)},
    ).json()["items"]
    assert [e for e in entries if e["action"] == "user.update"] == []


# ---------------------------------------------------------------------------
# Deactivation is immediate
# ---------------------------------------------------------------------------


def test_deactivation_kills_the_account_sessions(client, admin_token):
    created = _new_user(client, admin_token)
    token = _login(client, created["email"], "a-long-enough-password")
    assert client.get("/auth/me", headers=_auth(token)).status_code == 200

    r = client.patch(
        f"/users/{created['id']}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    # The point of deactivation: the token that was working a moment ago is
    # not valid on the very next request, rather than at its natural expiry.
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401

    # And they cannot sign in again.
    r = client.post(
        "/auth/login",
        json={"email": created["email"], "password": "a-long-enough-password"},
    )
    assert r.status_code == 401


def test_deactivation_is_audited_with_the_session_bump(client, admin_token):
    created = _new_user(client, admin_token)
    r = client.patch(
        f"/users/{created['id']}",
        headers=_auth(admin_token),
        json={"is_active": False},
    )
    assert r.status_code == 200, r.text

    entries = client.get(
        "/audit",
        headers=_auth(admin_token),
        params={"entity_type": "user", "entity_id": created["id"]},
    ).json()["items"]
    updates = [e for e in entries if e["action"] == "user.update"]
    assert len(updates) == 1
    assert updates[0]["before"]["is_active"] is True
    assert updates[0]["after"]["is_active"] is False
    assert updates[0]["after"]["sessions_invalidated"] is True
    assert updates[0]["actor_name"] == "Test Admin"


# ---------------------------------------------------------------------------
# CSV exports
# ---------------------------------------------------------------------------


def test_exports_require_authentication(client):
    for path in (
        "/farmers/export",
        "/deliveries/export",
        "/payments/export",
        "/audit/export",
    ):
        assert client.get(path).status_code == 401, path


def test_audit_export_is_admin_only(client, clerk_token):
    assert client.get("/audit/export", headers=_auth(clerk_token)).status_code == 403


def test_literal_export_path_is_not_parsed_as_a_uuid(client, clerk_token):
    """
    Route ordering regression guard.

    `/farmers/export` is declared before `/farmers/{farmer_id}`. If the order
    ever flips, FastAPI tries to parse "export" as a UUID and answers 422.
    """
    for path in ("/farmers/export", "/deliveries/export", "/payments/export"):
        r = client.get(path, headers=_auth(clerk_token))
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:120]}"


def test_farmers_export_matches_the_list_and_has_a_filename(
    client, clerk_token, farmer
):
    r = client.get(
        "/farmers/export",
        headers=_auth(clerk_token),
        params={"limit": 10},  # ignored: exports are not paginated
    )
    assert "attachment; filename=" in r.headers["content-disposition"]

    rows = _csv_rows(r)
    assert farmer.phone in [row["phone"] for row in rows]
    assert set(rows[0]) == {
        "id",
        "first_name",
        "last_name",
        "phone",
        "national_id",
        "date_of_birth",
        "location",
        "status",
        "verified_at",
        "registered_at",
    }


def test_export_applies_the_same_filters_as_the_list(client, clerk_token, farmer):
    r = client.get(
        "/farmers/export",
        headers=_auth(clerk_token),
        params={"search": farmer.phone},
    )
    rows = _csv_rows(r)
    assert len(rows) == 1
    assert rows[0]["phone"] == farmer.phone


def test_formula_like_text_is_neutralised_but_money_is_not(
    client, clerk_token, farmer, produce_line, rate
):
    """
    A note beginning with "=" would execute when the file is opened in Excel.
    It is prefixed with a tab; negative money must keep its leading minus so
    the column still sums.
    """
    r = client.post(
        "/deliveries",
        headers=_auth(clerk_token),
        json={
            "farmer_id": str(farmer.id),
            "produce_line_id": str(produce_line.id),
            "quantity": "12.5",
            "delivered_at": "2025-06-15T10:00:00Z",
            "notes": "=1+1",
        },
    )
    assert r.status_code == 201, r.text

    rows = _csv_rows(client.get("/deliveries/export", headers=_auth(clerk_token)))
    matching = [row for row in rows if row["id"] == r.json()["id"]]
    assert len(matching) == 1
    assert matching[0]["notes"].startswith("\t=")

    # Amount is untouched: still parseable as a number.
    assert float(matching[0]["amount"]) == pytest.approx(12.5 * 50.0)


def test_audit_export_carries_the_snapshot(client, admin_token, clerk, clerk_token):
    r = client.patch(
        f"/users/{clerk.id}",
        headers=_auth(admin_token),
        json={"full_name": "Renamed Clerk"},
    )
    assert r.status_code == 200, r.text

    rows = _csv_rows(
        client.get(
            "/audit/export",
            headers=_auth(admin_token),
            params={"entity_id": str(clerk.id)},
        )
    )
    updates = [row for row in rows if row["action"] == "user.update"]
    assert len(updates) == 1
    assert "Renamed Clerk" in updates[0]["after"]
