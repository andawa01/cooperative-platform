"""
Database engine + session factory.

We use SQLAlchemy 2.0 style. The engine manages a connection POOL — many
connections reused across requests, which is why we don't create one per
request (that would be slow and would exhaust Postgres).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# Engine: one per application. pool_pre_ping avoids "stale connection" errors
# after the DB restarts or idles out; pool_recycle bounds how long a
# connection may live behind a proxy that silently drops idle sockets.
#
# statement_timeout is enforced by Postgres itself, so it also applies to
# queries we did not write (a pathological JOIN, a lock wait). Without it a
# single stuck query holds its connection until the pool starves.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    connect_args={
        "options": f"-c statement_timeout={settings.db_statement_timeout_ms}"
    },
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
    time a service is called there is often already an open transaction —
    e.g. a caller reads a balance and then reverses a payment, or two service
    calls share one session. `Session.begin()` raises "A transaction is
    already begun on this Session" in that state, so it is closed out first.

    We **commit** rather than roll back. A rollback here silently discards
    writes the caller has already made — in the test suite that includes
    fixture rows still sitting in the surrounding savepoint, which then
    vanish mid-request and make update-only services operate on a row that
    no longer exists. Committing makes prior work durable before the
    service's own unit of work begins, which is what "the service owns its
    transaction" should mean.

    In tests, `join_transaction_mode="create_savepoint"` turns both the
    commit and the begin into savepoint operations on the surrounding
    transaction, so isolation still holds and teardown still rolls back.
    """
    if db.in_transaction():
        db.commit()
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
