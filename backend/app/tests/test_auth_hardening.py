"""
Auth hardening (D-030): throttling, revocation, password change, headers.

Redis is replaced with an in-memory fake so these tests are deterministic and
do not touch a developer's Redis. The fake implements only the commands the
auth code uses — if the code starts calling something else, the test fails
loudly instead of silently exercising the real store.
"""

import time

import pytest

from app.core.config import settings

# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def expire(self, key, ttl):
        self._ops.append(("expire", key, ttl))
        return self

    def setex(self, key, ttl, value):
        self._ops.append(("setex", key, ttl, value))
        return self

    def delete(self, key):
        self._ops.append(("delete", key))
        return self

    def execute(self):
        results = [getattr(self._redis, op[0])(*op[1:]) for op in self._ops]
        self._ops.clear()
        return results


class FakeRedis:
    """Just enough Redis for the throttle and the denylist."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[str, float | None]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def _live(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at <= self._now():
            self._data.pop(key, None)
            return None
        return value, expires_at

    def incr(self, key):
        live = self._live(key)
        value = int(live[0]) + 1 if live else 1
        expires_at = live[1] if live else None
        self._data[key] = (str(value), expires_at)
        return value

    def expire(self, key, ttl):
        live = self._live(key)
        if live is None:
            return False
        self._data[key] = (live[0], self._now() + ttl)
        return True

    def ttl(self, key):
        live = self._live(key)
        if live is None:
            return -2
        _value, expires_at = live
        if expires_at is None:
            return -1
        return int(expires_at - self._now())

    def setex(self, key, ttl, value):
        self._data[key] = (str(value), self._now() + ttl)
        return True

    def delete(self, key):
        return 1 if self._data.pop(key, None) is not None else 0

    def exists(self, key):
        return 1 if self._live(key) is not None else 0

    def pipeline(self):
        return FakePipeline(self)

    def ping(self):
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("app.services.login_throttle.redis_client", fake)
    monkeypatch.setattr("app.services.token_denylist.redis_client", fake)
    return fake


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


def _token(client, email, password) -> str:
    r = _login(client, email, password)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------


def test_repeated_failures_lock_the_account(client, admin, fake_redis):
    # Attempts below the threshold are ordinary credential rejections.
    for attempt in range(settings.login_max_attempts - 1):
        r = _login(client, admin.email, "definitely-wrong")
        assert r.status_code == 401, f"attempt {attempt + 1} should be 401"

    # The attempt that crosses the threshold answers 429 (with the wait)
    # instead of 401: the caller learns to stop rather than keep guessing.
    r = _login(client, admin.email, "definitely-wrong")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert "too many" in r.json()["detail"].lower()

    # The lock is checked before the password is verified, so the correct
    # password does not get through either.
    assert _login(client, admin.email, "password-123").status_code == 429


def test_successful_login_resets_the_failure_count(client, admin, fake_redis):
    for _ in range(settings.login_max_attempts - 1):
        assert _login(client, admin.email, "wrong").status_code == 401

    assert _login(client, admin.email, "password-123").status_code == 200

    # Counter was cleared, so a fresh run of failures starts from zero and the
    # last of these is still a 401 (not a lockout).
    for _ in range(settings.login_max_attempts - 1):
        r = _login(client, admin.email, "wrong")
    assert r.status_code == 401


def test_lockout_escalates_on_repeat(client, admin, fake_redis):
    # First lockout.
    for _ in range(settings.login_max_attempts):
        _login(client, admin.email, "wrong")
    first = _login(client, admin.email, "wrong")
    assert first.status_code == 429
    first_retry = int(first.headers["retry-after"])

    # Clear the lock to simulate the window expiring, then trip it again.
    for key in list(fake_redis._data):
        if ":lock:" in key:
            fake_redis.delete(key)

    for _ in range(settings.login_max_attempts):
        _login(client, admin.email, "wrong")
    second = _login(client, admin.email, "wrong")
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > first_retry


# ---------------------------------------------------------------------------
# Logout / revocation
# ---------------------------------------------------------------------------


def test_logout_revokes_only_that_token(client, admin, fake_redis):
    first = _token(client, admin.email, "password-123")
    second = _token(client, admin.email, "password-123")

    assert client.get("/auth/me", headers=_auth(first)).status_code == 200

    r = client.post("/auth/logout", headers=_auth(first))
    assert r.status_code == 204

    assert client.get("/auth/me", headers=_auth(first)).status_code == 401
    # A different session is unaffected.
    assert client.get("/auth/me", headers=_auth(second)).status_code == 200


# ---------------------------------------------------------------------------
# Password change
# ---------------------------------------------------------------------------


def test_password_change_requires_the_current_password(client, admin, fake_redis):
    token = _token(client, admin.email, "password-123")

    r = client.post(
        "/auth/password",
        headers=_auth(token),
        json={
            "current_password": "not-my-password",
            "new_password": "brand-new-password",
        },
    )
    assert r.status_code == 401


def test_password_change_invalidates_every_token(client, admin, fake_redis):
    old_token = _token(client, admin.email, "password-123")
    new_password = "brand-new-password-42"

    r = client.post(
        "/auth/password",
        headers=_auth(old_token),
        json={
            "current_password": "password-123",
            "new_password": new_password,
        },
    )
    assert r.status_code == 204, r.text

    # Every token minted under the old version is dead, including the one
    # that performed the change.
    assert client.get("/auth/me", headers=_auth(old_token)).status_code == 401

    # Old password no longer works; the new one does.
    assert _login(client, admin.email, "password-123").status_code == 401
    assert _login(client, admin.email, new_password).status_code == 200


def test_new_password_must_differ(client, admin, fake_redis):
    token = _token(client, admin.email, "password-123")

    r = client.post(
        "/auth/password",
        headers=_auth(token),
        json={
            "current_password": "password-123",
            "new_password": "password-123",
        },
    )
    assert r.status_code == 422


def test_registration_honours_the_same_revocation_rules(client, admin, fake_redis):
    """`/auth/register` has its own token guard (for bootstrap); it must not
    be a way around logout or a password change."""
    new_user = {
        "email": "revived@test.io",
        "full_name": "Revived User",
        "password": "a-long-enough-password",
        "role": "clerk",
    }

    revoked = _token(client, admin.email, "password-123")
    assert client.post("/auth/logout", headers=_auth(revoked)).status_code == 204
    r = client.post("/auth/register", headers=_auth(revoked), json=new_user)
    assert r.status_code == 401

    stale = _token(client, admin.email, "password-123")
    r = client.post(
        "/auth/password",
        headers=_auth(stale),
        json={
            "current_password": "password-123",
            "new_password": "post-change-password",
        },
    )
    assert r.status_code == 204
    r = client.post("/auth/register", headers=_auth(stale), json=new_user)
    assert r.status_code == 401

    # A live token still works, so the guard is not simply refusing everyone.
    fresh = _token(client, admin.email, "post-change-password")
    assert (
        client.post("/auth/register", headers=_auth(fresh), json=new_user).status_code
        == 201
    )


def test_short_new_password_is_rejected_by_validation(client, admin, fake_redis):
    token = _token(client, admin.email, "password-123")

    r = client.post(
        "/auth/password",
        headers=_auth(token),
        json={"current_password": "password-123", "new_password": "short"},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    # Never advertised over plain HTTP.
    assert "strict-transport-security" not in r.headers
