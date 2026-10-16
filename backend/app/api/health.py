"""
Health check endpoint.

Two levels:
- /health        — is the process alive?
- /health/db     — can we reach the database?

Keeping these separate means a load balancer can distinguish "app crashed"
from "app up but DB down."
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db

from app.core.redis_client import ping as redis_ping

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:
        return {"status": "error", "database": "unreachable", "detail": str(exc)}

@router.get("/health/redis")
def health_redis():
    ok = redis_ping()
    return {"status": "ok" if ok else "error", "redis": "reachable" if ok else "unreachable"}