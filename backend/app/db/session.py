"""
Database engine + session factory.

We use SQLAlchemy 2.0 style. The engine manages a connection POOL — many
connections reused across requests, which is why we don't create one per
request (that would be slow and would exhaust Postgres).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

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