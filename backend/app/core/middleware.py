"""
Request context: id propagation, access logging, and the 500 contract.

Written as raw ASGI rather than `BaseHTTPMiddleware` for two reasons: it adds
no task hop per request, and it can set headers on the response *start*
message without buffering the body.

Ordering note (in main.py): CORS is added after this middleware so it ends up
outside, meaning a 500 produced here still gets CORS headers. A browser that
cannot read the error body is a support ticket with no information in it.
"""

import logging
import re
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.logging import reset_request_id, set_request_id

log = logging.getLogger("app.request")

# An id we are willing to echo back: bounded length, no control characters,
# no spaces. Anything else is replaced — a caller must not be able to inject
# newlines into our logs or response headers.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _incoming_request_id(headers: Headers) -> str | None:
    value = headers.get("x-request-id")
    if value and _VALID_REQUEST_ID.match(value):
        return value
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = _incoming_request_id(headers) or str(uuid.uuid4())
        token = set_request_id(request_id)

        method = scope.get("method", "?")
        path = scope.get("path", "?")
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            log.exception(
                "unhandled exception",
                extra={
                    "method": method,
                    "path": path,
                    "status": 500,
                    "duration_ms": duration_ms,
                },
            )
            # If the response already started (streaming), we cannot replace
            # it; let the server abort the connection.
            if not response_started:
                response = JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Internal server error",
                        "request_id": request_id,
                    },
                    headers={"X-Request-ID": request_id},
                )
                await response(scope, receive, send)
        else:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            slow = duration_ms >= settings.slow_request_ms
            log.log(
                logging.WARNING if slow else logging.INFO,
                "request",
                extra={
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                },
            )
        finally:
            reset_request_id(token)


class SecurityHeadersMiddleware:
    """
    Baseline browser hardening headers on every response.

    No Content-Security-Policy: this service serves JSON, and the one HTML
    document it does serve (/docs, Swagger UI) needs inline scripts, so a
    strict CSP here would break the docs without protecting an API. When a
    separate frontend origin is served, CSP belongs there.

    HSTS is only sent over HTTPS; sending it over plain HTTP is ignored by
    browsers and would lock a developer out of localhost for a year.
    """

    _HEADERS = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "no-referrer",
        "cross-origin-opener-policy": "same-origin",
    }

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in self._HEADERS.items():
                    headers.setdefault(name, value)
                if scope.get("scheme") == "https":
                    headers.setdefault(
                        "strict-transport-security",
                        "max-age=31536000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:
    """
    Backstop handler.

    RequestContextMiddleware normally catches first, so this covers failures
    raised in middleware *above* it (or added later). Same body shape, same
    id, from the contextvar rather than the request object.
    """
    from app.core.logging import get_request_id

    request_id = get_request_id() or str(uuid.uuid4())
    log.error(
        "unhandled exception reached the server error handler",
        exc_info=exc,
        extra={"method": request.method, "path": request.url.path, "status": 500},
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )
