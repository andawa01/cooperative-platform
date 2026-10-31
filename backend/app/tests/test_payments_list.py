"""
Payments list: response contract and statement count.

The query-count test exists because this endpoint used to run two queries per
row (allocations + their sum). A page of 100 payments issued 201 statements.
Performance regressions like that are invisible in a passing response-body
assertion, so we count statements instead of timing anything.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import event

from app.core.security import create_access_token
from app.models.payment import PaymentMethod
from app.schemas.delivery import DeliveryCreate
from app.schemas.payment import PaymentCreate
from app.services import delivery as delivery_service
from app.services import payment as payment_service


def _auth_header(user) -> dict:
    tok = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {tok}"}


def _record_delivery(db, admin, farmer, produce_line, quantity: str = "10"):
    return delivery_service.record_delivery(
        db,
        DeliveryCreate(
            farmer_id=farmer.id,
            produce_line_id=produce_line.id,
            quantity=Decimal(quantity),
            delivered_at=datetime.now(UTC),
        ),
        admin,
    )


def _record_payment(db, admin, farmer, amount: str):
    payment, _replayed = payment_service.record_payment(
        db,
        PaymentCreate(
            farmer_id=farmer.id,
            amount=Decimal(amount),
            currency="KES",
            method=PaymentMethod.CASH,
            paid_at=datetime.now(UTC),
            idempotency_key=str(uuid.uuid4()),
        ),
        admin,
    )
    return payment


def _count_statements(db, call) -> int:
    """Run `call` and return how many SQL statements it issued."""
    statements: list[str] = []
    bind = db.get_bind()

    def before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", before_cursor_execute)
    try:
        call()
    finally:
        event.remove(bind, "before_cursor_execute", before_cursor_execute)
    return len(statements)


def test_list_returns_names_allocations_and_credit(
    client, admin, farmer, produce_line, rate, db
):
    delivery = _record_delivery(db, admin, farmer, produce_line, "10")  # 10 @ 50
    _record_payment(db, admin, farmer, "200")  # FIFO-allocated against it

    r = client.get("/payments?limit=10", headers=_auth_header(admin))
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total"] == 1
    payment = body["items"][0]
    assert payment["farmer_name"] == "Test Farmer"
    assert payment["farmer_id"] == str(farmer.id)
    assert Decimal(payment["unallocated_amount"]) == Decimal("0")
    assert len(payment["allocations"]) == 1
    assert Decimal(payment["allocations"][0]["amount"]) == Decimal("200")
    assert payment["allocations"][0]["delivery_id"] == str(delivery.id)


def test_page_statement_count_does_not_grow_with_rows(
    client, admin, farmer, produce_line, rate, db
):
    _record_delivery(db, admin, farmer, produce_line, "10")
    for _ in range(3):
        _record_payment(db, admin, farmer, "100")

    headers = _auth_header(admin)

    # Warm-up: in this suite the first query after a fixture opens the nested
    # test transaction, which SQLAlchemy emits as a SAVEPOINT. Counting that
    # against whichever request runs first would be measuring the fixture, not
    # the endpoint.
    client.get("/payments?limit=1", headers=headers)

    one = _count_statements(
        db, lambda: client.get("/payments?limit=1", headers=headers)
    )
    three = _count_statements(
        db, lambda: client.get("/payments?limit=3", headers=headers)
    )

    # Rendering a page is a fixed number of statements (auth lookup, count,
    # page select, farmers, allocations). One extra row must not cost extra
    # round trips.
    assert three == one, (
        f"limit=1 issued {one} statements, limit=3 issued {three}: "
        "the list is back to N+1 queries"
    )
