"""
Health endpoint contract tests.

The point of these is operational: a health check that answers 200 while a
dependency is down is worse than no health check at all, because every load
balancer and uptime monitor trusts the status line. These tests pin the
status code, not just the body.
"""

from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


class _BrokenSession:
    """Stands in for a Session whose connection has failed."""

    def execute(self, *args, **kwargs):
        # The message deliberately contains what a real driver error might:
        # a DSN with credentials. It must never reach the client.
        raise OperationalError(
            "SELECT 1",
            {},
            Exception("could not connect to postgresql://shamba:hunter2@db:5432/x"),
        )


def test_liveness_is_200(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_database_reachable_is_200(client):
    r = client.get("/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "reachable"}


def test_database_unreachable_is_503_and_leaks_nothing(client):
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: _BrokenSession()
    try:
        r = client.get("/health/db")
    finally:
        if previous is not None:
            app.dependency_overrides[get_db] = previous

    assert r.status_code == 503
    body = r.json()
    assert body["detail"] == "Database unreachable"
    # request_id is now present on all error responses (not just 500s).
    assert "request_id" in body
    # No DSN, host, user or password in the body.
    assert "hunter2" not in r.text
    assert "postgresql://" not in r.text


def test_redis_unreachable_is_503(client, monkeypatch):
    monkeypatch.setattr("app.api.health.redis_ping", lambda: False)

    r = client.get("/health/redis")
    assert r.status_code == 503
    body = r.json()
    assert body["detail"] == "Redis unreachable"
    assert "request_id" in body
