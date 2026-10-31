"""
Health check endpoints.

Three levels, deliberately separate:
- /health        — is the process alive? (liveness)
- /health/db     — can we reach the database? (readiness)
- /health/redis  — can we reach Redis? (readiness)

The distinction matters operationally: a load balancer should stop sending
traffic when a *dependency* is down (503), but must not kill a process that
is merely waiting for that dependency to come back (which is what a failing
liveness probe would do).

Error responses are 503, never 200. A health check that returns 200 with
`{"status": "error"}` in the body is invisible to every proxy and uptime
monitor that only reads the status line.

We do not echo the driver's exception text: it can contain the DSN, host
names and credentials. The detail is logged instead.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.redis_client import ping as redis_ping
from app.db.session import get_db

log = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    """Liveness: the process is up and serving."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    """Readiness: one round trip to Postgres."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 — any driver error means not ready
        log.exception("database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        )
    return {"status": "ok", "database": "reachable"}


@router.get("/health/redis")
def health_redis():
    """Readiness: one PING to Redis."""
    if not redis_ping():
        log.error("redis health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis unreachable",
        )
    return {"status": "ok", "redis": "reachable"}
