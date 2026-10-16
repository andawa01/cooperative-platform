"""
Permission boundary tests at the HTTP layer.

The brief explicitly names "permission boundaries" as one of the things
worth testing (see D-022). Every protected endpoint gets at least one
denial test.
"""
import uuid

from app.core.security import create_access_token


def _auth_header(user) -> dict:
    tok = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

def test_no_token_401(client):
    for path in ["/farmers", "/produce-lines", "/deliveries", "/payments"]:
        r = client.get(path)
        assert r.status_code == 401, f"{path} returned {r.status_code}"
        assert r.headers.get("www-authenticate") == "Bearer"


def test_bad_token_401(client):
    r = client.get("/farmers", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Authenticated but insufficient role
# ---------------------------------------------------------------------------

def test_clerk_cannot_create_produce_line(client, clerk):
    r = client.post(
        "/produce-lines",
        headers=_auth_header(clerk),
        json={"code": "x", "name": "X", "unit": "kg"},
    )
    assert r.status_code == 403


def test_clerk_cannot_reverse_payment(client, clerk):
    r = client.post(
        f"/payments/{uuid.uuid4()}/reverse",
        headers=_auth_header(clerk),
        json={"reason": "test"},
    )
    # Permission check runs before existence check, so 403 even if not found.
    assert r.status_code == 403


def test_clerk_cannot_reverse_delivery(client, clerk):
    r = client.post(
        f"/deliveries/{uuid.uuid4()}/reverse",
        headers=_auth_header(clerk),
        json={"reason": "test"},
    )
    assert r.status_code == 403


def test_clerk_cannot_update_farmer(client, clerk, farmer):
    r = client.patch(
        f"/farmers/{farmer.id}",
        headers=_auth_header(clerk),
        json={"notes": "x"},
    )
    assert r.status_code == 403


def test_admin_can_access(client, admin, db):
    from app.models.user import User
    assert db.get(User, admin.id) is not None, "admin fixture not in session"
    r = client.get("/farmers", headers=_auth_header(admin))
    assert r.status_code == 200, f"unexpected: {r.status_code} {r.text}"