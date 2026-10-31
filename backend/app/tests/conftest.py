"""
Pytest fixtures.

Two isolation strategies coexist here:

- Ordinary tests use a `db` fixture that opens a transaction and rolls it
  back at the end. The service's `with db.begin():` calls become SAVEPOINTs
  thanks to `join_transaction_mode="create_savepoint"`. Fast, isolated, and
  the test database stays pristine.

- Concurrency tests use `db_factory` to obtain independent sessions, each
  on its own connection. They commit for real, because concurrent
  correctness requires real database state. Cleanup is the test's
  responsibility; we provide `cleanup_farmer` as a helper.
"""

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.farmer import Farmer, FarmerStatus
from app.models.payment import Payment, PaymentAllocation  # noqa: F401
from app.models.produce import ProduceLine, Rate
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# Engine + schema (session scope)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_engine():
    """
    Engine bound to the test database. Created once per test session.

    We do NOT use the app's engine because we want a dedicated database.
    The schema is dropped and recreated at session start; individual tests
    do not touch DDL.
    """
    url = settings.database_url_test
    if not url:
        pytest.skip("DATABASE_URL_TEST is not set")
    engine = create_engine(url, future=True)
    # Import models so Base.metadata is populated (via conftest imports above).
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    return sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


# ---------------------------------------------------------------------------
# Ordinary tests: single rolled-back transaction
# ---------------------------------------------------------------------------


@pytest.fixture
def db(test_engine) -> Iterator[Session]:
    """
    A session inside a transaction that is rolled back at the end.

    `join_transaction_mode="create_savepoint"` makes the service's
    `with db.begin():` a savepoint, so real service code works unchanged
    inside tests.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# HTTP client (ordinary tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db: Session):
    """
    TestClient wired to the TEST database.

    The app's own `get_db` opens sessions on `settings.database_url`, so
    without this override every request would query a different database
    than the fixtures seeded — the token's user would not be found and a
    valid token would come back as 401 "Invalid token".

    We hand FastAPI the same session (and therefore the same transaction)
    the fixtures use, then drop the override afterwards so it cannot leak
    into other tests.
    """

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Concurrency tests: independent sessions per thread
# ---------------------------------------------------------------------------


@pytest.fixture
def db_factory(test_engine):
    """
    Returns a callable that creates a NEW session bound to the test engine.
    Each session manages its own connection and transaction lifecycle.
    Callers MUST call session.close() when done.

    Unlike the `db` fixture, sessions from this factory do NOT share a
    parent transaction. Commits are real. Locks are real. Isolation is real.
    This is required for the concurrency tests.
    """
    SessionLocal = sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    def _make() -> Session:
        return SessionLocal()

    return _make


@pytest.fixture
def cleanup_farmer(db_factory):
    """
    Helper: delete a farmer and every dependent row after a concurrency test.

    Concurrency tests commit for real, so we clean up explicitly.
    """
    created_ids: list[uuid.UUID] = []

    def _register(farmer_id: uuid.UUID):
        created_ids.append(farmer_id)

    yield _register

    if not created_ids:
        return
    s = db_factory()
    try:
        for fid in created_ids:
            # Order matters: allocations reference payments and deliveries.
            s.execute(
                text(
                    "DELETE FROM payment_allocations WHERE payment_id IN "
                    "(SELECT id FROM payments WHERE farmer_id = :fid) "
                    "OR delivery_id IN "
                    "(SELECT id FROM deliveries WHERE farmer_id = :fid)"
                ),
                {"fid": str(fid)},
            )
            s.execute(
                text("DELETE FROM payments WHERE farmer_id = :fid"),
                {"fid": str(fid)},
            )
            s.execute(
                text("DELETE FROM deliveries WHERE farmer_id = :fid"),
                {"fid": str(fid)},
            )
            s.execute(
                text("DELETE FROM farmers WHERE id = :fid"),
                {"fid": str(fid)},
            )
        s.commit()
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Seeded entities (ordinary tests)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin(db: Session) -> User:
    u = User(
        email=f"admin-{uuid.uuid4().hex[:8]}@test.io",
        full_name="Test Admin",
        hashed_password=hash_password("password-123"),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def clerk(db: Session) -> User:
    u = User(
        email=f"clerk-{uuid.uuid4().hex[:8]}@test.io",
        full_name="Test Clerk",
        hashed_password=hash_password("password-123"),
        role=UserRole.CLERK.value,
        is_active=True,
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def farmer(db: Session, clerk: User) -> Farmer:
    f = Farmer(
        first_name="Test",
        last_name="Farmer",
        phone=f"+2547{uuid.uuid4().int % 10**8:08d}",
        status=FarmerStatus.ACTIVE.value,
        created_by_id=clerk.id,
    )
    db.add(f)
    db.flush()
    return f


@pytest.fixture
def produce_line(db: Session, admin: User) -> ProduceLine:
    p = ProduceLine(
        code=f"coffee_{uuid.uuid4().hex[:6]}",
        name="Coffee",
        unit="kg",
        is_active=True,
        created_by_id=admin.id,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def rate(db: Session, produce_line: ProduceLine, admin: User) -> Rate:
    r = Rate(
        produce_line_id=produce_line.id,
        rate_per_unit=Decimal("50.0000"),
        currency="KES",
        effective_from=date(2025, 1, 1),
        effective_to=None,
        created_by_id=admin.id,
    )
    db.add(r)
    db.flush()
    return r
