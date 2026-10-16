"""
FastAPI application entry point.

Keep this file TINY. It wires together routers and middleware — nothing else.
Business logic lives in services; HTTP handlers live in api/.
"""
from fastapi import FastAPI

from app.api import auth, deliveries, farmers, health, notifications, payments, produce, statements
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="ShambaTrack API",
        version="0.1.0",
        description="Cooperative management platform for East African agriculture.",
    )

    # Register routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(farmers.router)
    app.include_router(produce.router)
    app.include_router(deliveries.router)
    app.include_router(payments.router)
    app.include_router(statements.router)
    app.include_router(notifications.router)
    return app


app = create_app()