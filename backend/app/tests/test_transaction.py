"""
`write_transaction` must not destroy work that already happened.

Regression test for a real bug: closing out the caller's open transaction with
a rollback discarded rows the test fixtures had flushed (they live inside the
surrounding savepoint), so an update-only service updated zero rows and the
data disappeared mid-request. Calling it with an existing `admin` fixture is
the exact shape that failed.
"""

from app.db.session import write_transaction
from app.models.user import User


def test_write_transaction_preserves_existing_rows(db, admin):
    with write_transaction(db):
        pass

    assert db.get(User, admin.id) is not None


def test_write_transaction_commits_its_own_work(db, admin):
    with write_transaction(db):
        admin.full_name = "Renamed In Service"

    db.refresh(admin)
    assert admin.full_name == "Renamed In Service"


def test_write_transaction_is_composable(db, admin):
    """A read before the write, then the write — the caller's shape."""
    assert db.get(User, admin.id) is not None

    with write_transaction(db):
        admin.full_name = "Composed"

    db.refresh(admin)
    assert admin.full_name == "Composed"
