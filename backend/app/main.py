from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    audit,
    auth,
    dashboard,
    deductions,
    deliveries,
    farmers,
    health,
    notifications,
    payments,
    produce,
    statements,
    users,
)
from app.core.config import settings
from app.core.logging import configure_logging, get_request_id
from app.core.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    unhandled_exception_handler,
)


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="ShambaTrack API",
        version="0.1.0",
        description="Cooperative management platform for East African agriculture.",
    )

    # Middleware order: the last one added is the outermost. Request context
    # goes on first so CORS wraps it — a 500 from the context middleware must
    # still reach the browser with CORS headers.
    app.add_middleware(RequestContextMiddleware)

    # Origins come from configuration (CORS_ORIGINS), so deploying a new
    # frontend origin is an env change, not a code change.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        # Both are read by the frontend: the replay flag and the id a clerk
        # can quote when reporting a failure.
        # Content-Disposition is exposed so CSV exports can use the filename
        # the server chose rather than inventing one in the browser.
        expose_headers=["Idempotency-Replayed", "X-Request-ID", "Content-Disposition"],
    )

    # Outermost: headers must be on every response, including the 500s and
    # CORS preflights produced by the layers below.
    app.add_middleware(SecurityHeadersMiddleware)

    # Standardize error responses: inject request_id into every HTTPException
    # body so clients always have a correlation key to quote, not just on 500s.
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,  # noqa: ARG001 - FastAPI signature requires it
        exc: HTTPException,
    ) -> JSONResponse:
        request_id = get_request_id()
        content: dict = {"detail": exc.detail}
        if request_id:
            content["request_id"] = request_id
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers,
        )

    # Backstop for failures raised above RequestContextMiddleware.
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(farmers.router)
    app.include_router(produce.router)
    app.include_router(deliveries.router)
    app.include_router(payments.router)
    app.include_router(statements.router)
    app.include_router(notifications.router)
    app.include_router(audit.router)
    app.include_router(users.router)
    app.include_router(deductions.router)

    return app


app = create_app()
