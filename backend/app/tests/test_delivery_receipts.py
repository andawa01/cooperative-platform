"""
Delivery receipt numbers (backlog 0.5).

What these hold the implementation to:

- Every delivery gets a short number a member can read over the phone, and the
  numbers run 1, 2, 3 within a calendar year.
- A new year restarts at 1 rather than continuing, so the year is visible in
  the number itself.
- A reversal carries no number: it corrects a slip, it is not one.
- The number reaches the places it is useful — the SMS the member receives and
  the CSV the accountant closes the month with.
"""

import csv
import io
from datetime import UTC, datetime

from app.core.security import create_access_token
from app.models.notification import Notification

DELIVERED_AT = datetime(2025, 6, 1, 10, 0, tzinfo=UTC)


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _record(client, user, farmer, produce_line, delivered_at=DELIVERED_AT) -> dict:
    r = client.post(
        "/deliveries",
        json={
            "farmer_id": str(farmer.id),
            "produce_line_id": str(produce_line.id),
            "quantity": "10",
            "delivered_at": delivered_at.isoformat(),
        },
        headers=_auth(user),
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_receipt_numbers_are_sequential(client, clerk, farmer, produce_line, rate):
    first = _record(client, clerk, farmer, produce_line)
    second = _record(client, clerk, farmer, produce_line)

    assert first["receipt_number"] == "D-2025-000001"
    assert second["receipt_number"] == "D-2025-000002"


def test_receipt_numbers_restart_each_year(client, clerk, farmer, produce_line, rate):
    in_2025 = _record(client, clerk, farmer, produce_line)
    # The rate fixture is open-ended, so 2026 is valued too.
    in_2026 = _record(
        client, clerk, farmer, produce_line, datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    )

    assert in_2025["receipt_number"] == "D-2025-000001"
    assert in_2026["receipt_number"] == "D-2026-000001"
    assert in_2025["receipt_number"] != in_2026["receipt_number"]


def test_reversal_has_no_receipt_number(client, admin, farmer, produce_line, rate):
    original = _record(client, admin, farmer, produce_line)

    r = client.post(
        f"/deliveries/{original['id']}/reverse",
        json={"reason": "weight keyed wrong"},
        headers=_auth(admin),
    )

    assert r.status_code == 201, r.text
    reversal = r.json()
    assert reversal["reversal_of_id"] == original["id"]
    assert reversal["receipt_number"] is None


def test_delivery_sms_quotes_the_receipt(client, db, clerk, farmer, produce_line, rate):
    delivery = _record(client, clerk, farmer, produce_line)

    notice = (
        db.query(Notification)
        .filter(Notification.related_entity_id == delivery["id"])
        .one()
    )

    assert delivery["receipt_number"] in notice.content
    assert "Receipt" in notice.content


def test_export_carries_the_receipt_number(client, clerk, farmer, produce_line, rate):
    delivery = _record(client, clerk, farmer, produce_line)

    r = client.get("/deliveries/export", headers=_auth(clerk))

    assert r.status_code == 200, r.text
    # The export prepends a BOM so Excel opens UTF-8 correctly (app/api/csv.py).
    text = r.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    row = next(row for row in rows if row["id"] == delivery["id"])
    assert row["receipt_number"] == delivery["receipt_number"]
