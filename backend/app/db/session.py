"""
Database engine + session factory.

We use SQLAlchemy 2.0 style. The engine manages a connection POOL — many
connections reused across requests, which is why we don't create one per
request (that would be slow and would exhaust Postgres).
"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

from app.core.config import settings


# Engine: one per application. pool_pre_ping avoids "stale connection" errors
# after the DB restarts or idles out.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=False,  # set True to see every SQL statement — useful when debugging
)

# Session factory. Each request gets its own session (see get_db below).
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


# SQLAlchemy 2.0 style base. All models inherit from this.
class Base(DeclarativeBase):
    pass


@contextmanager
def write_transaction(db: Session) -> Iterator[None]:
    """
    Open a service's write transaction, even if the session is mid-transaction.

    A Session starts a transaction implicitly on the first query, so by the
    time a service is called there is often already an open (read-only)
    transaction — e.g. a caller reads a balance and then reverses a payment,
    or two service calls share one session. `Session.begin()` raises
    "A transaction is already begun on this Session" in that state, so we
    close out anything pending first.

    The service then owns and commits its own unit of work, exactly as it
    does in a request. In tests, a savepoint-joined session turns that commit
    into a savepoint release, so the surrounding test transaction can still
    roll everything back.

    NOTE: closing a savepoint-joined session via rollback leaves the outer
    transaction intact and is safe in both production and test isolation paths.
    """
    if db.is_active:
        db.rollback()
    with db.begin():
        yield


def get_db():
    """
    FastAPI dependency: yields a session per request, always closes it.

    Why this shape? FastAPI dependencies with `yield` run cleanup after the
    request finishes — the `finally` block guarantees the session is closed
    even if the endpoint raises.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()