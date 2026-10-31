"""
Structured logging.

Every log line the API emits is one JSON object on stdout, which is what log
shippers (Loki, CloudWatch, Datadog) actually parse. Human-readable output is
available with LOG_FORMAT=plain for local work.

The request id lives in a `ContextVar`, so any log call made while handling a
request — in the router, a service, or a deep library call — is automatically
tagged with the id the client can quote to support. Nothing has to be threaded
through function signatures.

Configuration is additive: we attach our handler to the root logger without
removing existing handlers. Clobbering root handlers would silently disable
pytest's log capture (and any embedding host's logging).
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# Set by RequestContextMiddleware for the duration of one request.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Record attributes that are promoted to top-level JSON fields. Keeping an
# allowlist (rather than dumping __dict__) means a library's internal
# attributes never leak into the stream.
_STRUCTURED_FIELDS = (
    "method",
    "path",
    "status",
    "duration_ms",
    "client",
    "event",
)


def set_request_id(value: str):
    return request_id_var.set(value)


def reset_request_id(token) -> None:
    request_id_var.reset(token)


def get_request_id() -> str | None:
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Never raises on formatting."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None) or request_id_var.get()
        if request_id:
            payload["request_id"] = request_id

        for field in _STRUCTURED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


class PlainFormatter(logging.Formatter):
    """Readable single line, with the request id appended when present."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = getattr(record, "request_id", None) or request_id_var.get()
        return f"{base} request_id={request_id}" if request_id else base


_HANDLER_MARKER = "_shambatrack_handler"


def configure_logging() -> None:
    """
    Install the application's log handler once per process.

    Idempotent: create_app() may run more than once (tests, multiple workers'
    imports), and a second handler would double every line.
    """
    root = logging.getLogger()
    if any(getattr(h, _HANDLER_MARKER, False) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if settings.log_json
        else PlainFormatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    setattr(handler, _HANDLER_MARKER, True)

    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
