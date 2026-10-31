"""
Audit trail tests (D-031).

The properties under test are the ones the trail exists for:

1. An entry exists for every money-affecting action, in the same
   transaction as the action — so a failure leaves no entry, and a success
   can never be missing one.
2. It names the actor and links to the request id from D-029.
3. Nothing is written twice (idempotent replay) and nothing is written
   when nothing happened (a rejected second reversal).
4. The table itself refuses UPDATE and DELETE.

Scope note: assertions always filter to a specific entity or action rather
than counting the whole table — concurrency tests commit real rows that are
still present when these run.
"""

import uuid
from decimal import Decimal

import pytest

from app.models.audit import AuditLog

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, email: str, password: str = "password-123") -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _entries(client, admin_token: str, **params) -> list[dict]:
    """GET /audit with filters, newest first."""
    r = client.get("/audit", headers=_auth(admin_token), params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _record_delivery(client, clerk_token, farmer, produce_line) -> tuple[dict, str]:
    r = client.post(
        "/deliveries",
        headers=_auth(clerk_token),
        json={
            "farmer_id": str(farmer.id),
            "produce_line_id": str(produce_line.id),
            "quantity": "10.5",
            "delivered_at": "2025-06-15T10:00:00Z",
            "notes": "morning harvest",
        },
    )
    assert r.status_code == 201, r.text
    return r.json(), r.headers["X-Request-ID"]


@pytest.fixture
def admin_token(client, admin) -> str:
    return _login(client, admin.email)


@pytest.fixture
def clerk_token(client, clerk) -> str:
    return _login(client, clerk.email)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def test_delivery_creation_is_logged_with_actor_and_request_id(
    client, admin_token, clerk_token, farmer, produce_line, rate
):
    delivery, request_id = _record_delivery(client, clerk_token, farmer, produce_line)

    entries = _entries(
        client,
        admin_token,
        entity_type="delivery",
        entity_id=delivery["id"],
    )
    assert len(entries) == 1

    entry = entries[0]
    assert entry["action"] == "delivery.create"
    assert entry["actor_name"] == "Test Clerk"
    # Ties the trail back to the exact request line in the logs (D-029).
    assert entry["request_id"] == request_id
    assert entry["before"] is None
    assert entry["after"]["quantity"] == "10.5"
    assert entry["after"]["pending_valuation"] is False
    assert entry["after"]["rate_snapshot"] is not None


def test_delivery_reversal_logs_the_original_delivery(
    client, admin_token, clerk_token, farmer, produce_line, rate
):
    delivery, _ = _record_delivery(client, clerk_token, farmer, produce_line)

    r = client.post(
        f"/deliveries/{delivery['id']}/reverse",
        headers=_auth(admin_token),
        json={"reason": "wrong weight entered"},
    )
    assert r.status_code < 300, r.text

    entries = _entries(
        client, admin_token, entity_type="delivery", entity_id=delivery["id"]
    )
    reversals = [e for e in entries if e["action"] == "delivery.reverse"]
    assert len(reversals) == 1

    entry = reversals[0]
    assert entry["actor_name"] == "Test Admin"
    assert entry["before"]["reversed"] is False
    assert entry["after"]["reversed"] is True
    assert entry["after"]["reason"] == "wrong weight entered"
    assert entry["after"]["reversal_id"]


def test_rejected_second_reversal_writes_no_entry(
    client, admin_token, clerk_token, farmer, produce_line, rate
):
    delivery, _ = _record_delivery(client, clerk_token, farmer, produce_line)

    r = client.post(
        f"/deliveries/{delivery['id']}/reverse",
        headers=_auth(admin_token),
        json={"reason": "first reversal"},
    )
    assert r.status_code < 300, r.text

    r = client.post(
        f"/deliveries/{delivery['id']}/reverse",
        headers=_auth(admin_token),
        json={"reason": "second reversal"},
    )
    assert r.status_code == 409, r.text

    # The failed attempt left no trace: the trail never claims a reversal
    # that the database does not contain.
    entries = _entries(
        client, admin_token, entity_type="delivery", entity_id=delivery["id"]
    )
    assert len([e for e in entries if e["action"] == "delivery.reverse"]) == 1


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


def _record_payment(client, token, farmer, key: str, amount: str = "100.00") -> dict:
    r = client.post(
        "/payments",
        headers=_auth(token),
        json={
            "farmer_id": str(farmer.id),
            "amount": amount,
            "currency": "KES",
            "method": "cash",
            "paid_at": "2025-06-20T09:00:00Z",
            "idempotency_key": key,
        },
    )
    assert r.status_code < 300, r.text
    return r.json()


def test_payment_is_logged_once_even_when_replayed(
    client, admin_token, clerk_token, farmer
):
    key = uuid.uuid4().hex
    first = _record_payment(client, clerk_token, farmer, key)
    replay = _record_payment(client, clerk_token, farmer, key)
    assert first["id"] == replay["id"]

    entries = _entries(
        client, admin_token, entity_type="payment", entity_id=first["id"]
    )
    creates = [e for e in entries if e["action"] == "payment.create"]
    assert len(creates) == 1, "an idempotent replay must not look like a 2nd payment"

    entry = creates[0]
    assert Decimal(entry["after"]["amount"]) == Decimal("100.00")
    assert entry["after"]["currency"] == "KES"
    assert entry["after"]["method"] == "cash"
    assert "unallocated_amount" in entry["after"]


def test_payment_reversal_is_logged_against_the_original(
    client, admin_token, clerk_token, farmer, produce_line, rate
):
    payment = _record_payment(client, clerk_token, farmer, uuid.uuid4().hex)

    r = client.post(
        f"/payments/{payment['id']}/reverse",
        headers=_auth(admin_token),
        json={"reason": "paid twice"},
    )
    assert r.status_code < 300, r.text

    entries = _entries(
        client, admin_token, entity_type="payment", entity_id=payment["id"]
    )
    reversals = [e for e in entries if e["action"] == "payment.reverse"]
    assert len(reversals) == 1
    # Compare numerically: the DB column is Numeric(12, 4), so the scale is
    # "100.0000" on the way out and "100.00" on the way in.
    assert Decimal(reversals[0]["before"]["amount"]) == Decimal("100.00")
    assert reversals[0]["after"]["reason"] == "paid twice"
    assert reversals[0]["actor_name"] == "Test Admin"


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------


def test_rate_change_records_the_old_and_new_price(
    client, admin_token, produce_line, rate
):
    r = client.post(
        f"/produce-lines/{produce_line.id}/rates",
        headers=_auth(admin_token),
        json={
            "rate_per_unit": "60.50",
            "currency": "KES",
            "effective_from": "2025-06-01",
        },
    )
    assert r.status_code < 300, r.text
    new_rate = r.json()["new_rate"]

    entries = _entries(
        client, admin_token, entity_type="rate", entity_id=new_rate["id"]
    )
    assert len(entries) == 1

    entry = entries[0]
    assert entry["action"] == "rate.create"
    # The fixture rate was 50.0000, open-ended from 2025-01-01.
    assert entry["before"]["rate_per_unit"] == "50.0000"
    assert entry["after"]["rate_per_unit"] == "60.50"
    assert entry["after"]["produce_line_id"] == str(produce_line.id)
    assert entry["actor_name"] == "Test Admin"


# ---------------------------------------------------------------------------
# Farmers
# ---------------------------------------------------------------------------


def _create_farmer(client, token, last_name="Audited") -> dict:
    r = client.post(
        "/farmers",
        headers=_auth(token),
        json={
            "first_name": "Trail",
            "last_name": last_name,
            "phone": f"+2547{uuid.uuid4().int % 10**8:08d}",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_farmer_lifecycle_is_logged_per_state_change(
    client, admin_token, clerk_token, farmer
):
    created = _create_farmer(client, clerk_token)
    created_entries = _entries(
        client, admin_token, entity_type="farmer", entity_id=created["id"]
    )
    assert created_entries[0]["action"] == "farmer.create"
    assert created_entries[0]["actor_name"] == "Test Clerk"
    assert created_entries[0]["before"] is None

    # Update: only the changed fields appear in the payload.
    r = client.patch(
        f"/farmers/{farmer.id}",
        headers=_auth(admin_token),
        json={"location": "Nyeri", "notes": "first note"},
    )
    assert r.status_code == 200, r.text

    # A second PATCH that changes nothing writes nothing.
    r = client.patch(
        f"/farmers/{farmer.id}",
        headers=_auth(admin_token),
        json={"location": "Nyeri"},
    )
    assert r.status_code == 200, r.text

    entries = _entries(client, admin_token, entity_type="farmer", entity_id=farmer.id)
    updates = [e for e in entries if e["action"] == "farmer.update"]
    assert len(updates) == 1, "a no-op PATCH must not produce an entry"
    assert set(updates[0]["before"]) == {"location", "notes"}
    assert updates[0]["after"]["location"] == "Nyeri"
    assert updates[0]["actor_name"] == "Test Admin"

    r = client.post(f"/farmers/{farmer.id}/verify", headers=_auth(admin_token))
    assert r.status_code < 300, r.text
    r = client.post(f"/farmers/{farmer.id}/archive", headers=_auth(admin_token))
    assert r.status_code < 300, r.text

    entries = _entries(client, admin_token, entity_type="farmer", entity_id=farmer.id)
    by_action = {e["action"]: e for e in entries}

    verify = by_action["farmer.verify"]
    assert verify["before"]["status"] == "active"  # fixture farmer is active
    assert verify["after"]["verified_at"] is not None

    archive = by_action["farmer.archive"]
    assert archive["before"]["status"] == "active"
    assert archive["after"]["status"] == "archived"


def test_farmer_archive_is_idempotent_and_logged_once(client, admin_token, farmer):
    for _ in range(2):
        r = client.post(f"/farmers/{farmer.id}/archive", headers=_auth(admin_token))
        assert r.status_code < 300, r.text

    entries = _entries(client, admin_token, entity_type="farmer", entity_id=farmer.id)
    archives = [e for e in entries if e["action"] == "farmer.archive"]
    assert len(archives) == 1, "archiving twice is one state change, one entry"
    assert archives[0]["after"]["status"] == "archived"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_user_creation_and_password_change_are_logged(client, admin, admin_token):
    email = f"audited-{uuid.uuid4().hex[:8]}@test.io"
    r = client.post(
        "/auth/register",
        headers=_auth(admin_token),
        json={
            "email": email,
            "full_name": "Audited User",
            "password": "a-long-enough-password",
            "role": "clerk",
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()

    entries = _entries(client, admin_token, entity_type="user", entity_id=created["id"])
    creates = [e for e in entries if e["action"] == "user.create"]
    assert len(creates) == 1
    assert creates[0]["actor_name"] == admin.full_name
    assert creates[0]["after"]["email"] == email
    assert creates[0]["after"]["role"] == "clerk"
    assert creates[0]["after"]["bootstrap"] is False

    # Change that user's password (self-service).
    token = _login(client, email, "a-long-enough-password")
    r = client.post(
        "/auth/password",
        headers=_auth(token),
        json={
            "current_password": "a-long-enough-password",
            "new_password": "another-long-enough-pw",
        },
    )
    assert r.status_code == 204, r.text

    entries = _entries(client, admin_token, entity_type="user", entity_id=created["id"])
    changes = [e for e in entries if e["action"] == "user.password_change"]
    assert len(changes) == 1
    assert changes[0]["after"]["sessions_invalidated"] is True

    # No secret material ever enters the trail, in either direction.
    for entry in entries:
        payload = str(entry.get("before")) + str(entry.get("after"))
        assert "password" not in payload.lower()
        assert "hashed" not in payload.lower()


# ---------------------------------------------------------------------------
# Access control and filters
# ---------------------------------------------------------------------------


def test_audit_is_admin_only(client, clerk_token, clerk, farmer):
    assert client.get("/audit").status_code == 401
    r = client.get("/audit", headers=_auth(clerk_token))
    assert r.status_code == 403


def test_filters_narrow_to_one_entity_and_one_action(
    client, admin_token, clerk, clerk_token, farmer, produce_line, rate
):
    delivery, _ = _record_delivery(client, clerk_token, farmer, produce_line)
    payment = _record_payment(client, clerk_token, farmer, uuid.uuid4().hex)

    by_entity = _entries(
        client, admin_token, entity_type="delivery", entity_id=delivery["id"]
    )
    assert [e["action"] for e in by_entity] == ["delivery.create"]

    by_actor = _entries(client, admin_token, actor_id=str(clerk.id))
    actions = {e["action"] for e in by_actor}
    assert {"delivery.create", "payment.create"} <= actions
    assert all(e["actor_name"] == "Test Clerk" for e in by_actor)

    by_action = _entries(client, admin_token, action="payment.create")
    assert all(e["entity_type"] == "payment" for e in by_action)
    assert payment["id"] in [e["entity_id"] for e in by_action]


def test_unknown_filter_values_are_rejected(client, admin_token):
    assert (
        client.get(
            "/audit", headers=_auth(admin_token), params={"action": "not.a.real.action"}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/audit",
            headers=_auth(admin_token),
            params={"entity_type": "unrelated"},
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# Append-only, enforced by the database
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def audit_immutable_trigger(test_engine):
    """
    Production gets this trigger from migration 5d0cf426e30a. The test schema
    comes from `Base.metadata.create_all`, which cannot express triggers, so
    install the same DDL here — otherwise this suite would test a table the
    real deployment does not have. Keep in sync with the migration.
    """
    from sqlalchemy import text

    with test_engine.begin() as conn:
        conn.execute(
            text(
                """
            CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'audit_log is append-only: % is not permitted', TG_OP;
            END;
            $$ LANGUAGE plpgsql
            """
            )
        )
        conn.execute(
            text(
                """
            DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log
            """
            )
        )
        conn.execute(
            text(
                """
            CREATE TRIGGER trg_audit_log_immutable
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_immutable()
            """
            )
        )
    yield
    with test_engine.begin() as conn:
        conn.execute(
            text("DROP TRIGGER IF EXISTS trg_audit_log_immutable ON audit_log")
        )
        conn.execute(text("DROP FUNCTION IF EXISTS audit_log_immutable()"))


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_log SET action = 'farmer.create' WHERE id = :id",
        "DELETE FROM audit_log WHERE id = :id",
    ],
    ids=["update", "delete"],
)
def test_audit_rows_cannot_be_modified_or_deleted(
    db, audit_immutable_trigger, statement
):
    from sqlalchemy import text

    entry = AuditLog(
        actor_id=None,
        action="farmer.create",
        entity_type="farmer",
        entity_id=uuid.uuid4(),
        after={"status": "pending_verification"},
    )
    db.add(entry)
    db.flush()

    with pytest.raises(Exception, match="append-only"):
        db.execute(text(statement), {"id": str(entry.id)})

    # The failed statement aborts the transaction; clear it so the fixture's
    # teardown is a clean rollback rather than an error.
    db.rollback()
