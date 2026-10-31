"""
Observability contract.

Three properties are load-bearing for support and for debugging production:

1. Every response carries a request id, and a caller-supplied id is echoed
   (so a client can correlate its own trace).
2. An unhandled exception returns a JSON body containing that id — not a
   stack trace, not an empty 500 — because "what were you doing at 14:02?"
   is answerable only if the clerk has something to quote.
3. Log lines are one JSON object per record, tagged with the request id.
"""

import json
import logging

from app.api.deps import get_current_user
from app.core.logging import JsonFormatter, request_id_var
from app.main import app

# ---------------------------------------------------------------------------
# Request id
# ---------------------------------------------------------------------------


def test_request_id_is_generated(client):
    r = client.get("/health")
    assert r.status_code == 200
    request_id = r.headers.get("x-request-id")
    assert request_id, "every response must carry a request id"
    assert len(request_id) >= 8


def test_supplied_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["x-request-id"] == "trace-abc-123"


def test_unsafe_request_id_is_replaced(client):
    # A value that could inject a header or a log line must not be echoed.
    hostile = "abc\tdef"
    r = client.get("/health", headers={"X-Request-ID": hostile})
    assert r.headers["x-request-id"] != hostile
    assert r.headers["x-request-id"]


# ---------------------------------------------------------------------------
# 500 contract
# ---------------------------------------------------------------------------


def _boom():
    raise RuntimeError("kaboom: password=hunter2 host=db.internal")


def test_unhandled_exception_returns_json_with_request_id(client):
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _boom
    try:
        r = client.get("/farmers", headers={"X-Request-ID": "trace-500"})
    finally:
        if previous is not None:
            app.dependency_overrides[get_current_user] = previous
        else:
            app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 500
    body = r.json()
    assert body == {
        "detail": "Internal server error",
        "request_id": "trace-500",
    }
    # Nothing from the exception reaches the client.
    assert "kaboom" not in r.text
    assert "hunter2" not in r.text


# ---------------------------------------------------------------------------
# Log shape
# ---------------------------------------------------------------------------


def test_json_formatter_emits_structured_record():
    token = request_id_var.set("rid-42")
    try:
        record = logging.LogRecord(
            name="app.request",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request",
            args=None,
            exc_info=None,
        )
        record.method = "GET"
        record.path = "/farmers"
        record.status = 200
        record.duration_ms = 12.5

        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert payload["message"] == "request"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == "rid-42"
    assert payload["method"] == "GET"
    assert payload["path"] == "/farmers"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 12.5
    assert "ts" in payload


def test_json_formatter_includes_traceback_without_crashing():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="app.request",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="unhandled exception",
            args=None,
            exc_info=sys.exc_info(),
        )
        payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert "ValueError: boom" in payload["exc_info"]
