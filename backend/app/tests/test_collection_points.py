"""Collection points, farmer/delivery assignment and production reporting (D-039).

What these hold the implementation to:

- A point is reference data with a unique, canonical code; retiring one stops
  new assignments but never rewrites history.
- A delivery carries the point it happened at, independent of where the member
  is registered today; omitting it inherits the member's point, which is what
  a clerk at intake expects.
- The production report shows net intake per point and never hides rows that
  have no point.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.core.security import create_access_token


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _point(client, admin, code: str = "KSM-CENTRAL", name: str = "Kisumu Central"):
    r = client.post(
        "/collection-points",
        json={
            "name": name,
            "code": code,
            "county": "Kisumu",
            "ward": "Kisumu Central",
            "zone": "Zone A",
        },
        headers=_auth(admin),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client, admin, farmer, point):
    r = client.patch(
        f"/farmers/{farmer.id}",
        json={"collection_point_id": point["id"]},
        headers=_auth(admin),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _deliver(client, user, farmer, produce_line, quantity: str, point_id=None):
    body = {
        "farmer_id": str(farmer.id),
        "produce_line_id": str(produce_line.id),
        "quantity": quantity,
        "delivered_at": datetime.now(UTC).isoformat(),
    }
    if point_id is not None:
        body["collection_point_id"] = point_id
    r = client.post("/deliveries", json=body, headers=_auth(user))
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list_points(client, admin, clerk):
    point = _point(client, admin)

    assert point["code"] == "KSM-CENTRAL"
    assert point["is_active"] is True

    listed = client.get("/collection-points", headers=_auth(clerk))
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["name"] == "Kisumu Central"


def test_a_duplicate_code_is_refused(client, admin):
    _point(client, admin, code="KSM-CENTRAL")

    r = client.post(
        "/collection-points",
        json={"name": "Another shed", "code": "ksm-central"},
        headers=_auth(admin),
    )

    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]


def test_codes_are_canonicalised(client, admin):
    point = _point(client, admin, code="  ksm-west  ")

    assert point["code"] == "KSM-WEST"


def test_a_clerk_cannot_create_a_point(client, clerk):
    r = client.post(
        "/collection-points",
        json={"name": "Kisumu Central", "code": "KSM-CENTRAL"},
        headers=_auth(clerk),
    )

    assert r.status_code == 403


def test_a_farmer_can_be_assigned_to_a_point(client, admin, farmer):
    point = _point(client, admin)

    updated = _assign(client, admin, farmer, point)

    assert updated["collection_point_id"] == point["id"]

    listed = client.get(
        "/farmers",
        params={"collection_point_id": point["id"]},
        headers=_auth(admin),
    )
    assert listed.json()["total"] == 1


def test_an_unknown_point_cannot_be_assigned(client, admin, farmer):
    r = client.patch(
        f"/farmers/{farmer.id}",
        json={"collection_point_id": str(uuid.uuid4())},
        headers=_auth(admin),
    )

    assert r.status_code == 422
    assert "Collection point" in r.json()["detail"]


def test_a_retired_point_cannot_take_new_members(client, admin, farmer):
    point = _point(client, admin)
    retired = client.patch(
        f"/collection-points/{point['id']}",
        json={"is_active": False},
        headers=_auth(admin),
    )
    assert retired.status_code == 200, retired.text

    r = client.patch(
        f"/farmers/{farmer.id}",
        json={"collection_point_id": point["id"]},
        headers=_auth(admin),
    )

    assert r.status_code == 409
    assert "inactive" in r.json()["detail"]


def test_a_delivery_inherits_the_farmers_point(
    client, admin, farmer, produce_line, rate
):
    point = _point(client, admin)
    _assign(client, admin, farmer, point)

    delivery = _deliver(client, admin, farmer, produce_line, "10")

    assert delivery["collection_point_id"] == point["id"]
    assert delivery["collection_point_name"] == "Kisumu Central"


def test_a_delivery_can_name_a_different_point(
    client, admin, farmer, produce_line, rate
):
    home = _point(client, admin, code="KSM-CENTRAL")
    other = _point(client, admin, code="KSM-WEST", name="Kisumu West")
    _assign(client, admin, farmer, home)

    delivery = _deliver(client, admin, farmer, produce_line, "10", point_id=other["id"])

    assert delivery["collection_point_id"] == other["id"]
    assert delivery["collection_point_name"] == "Kisumu West"


def test_deliveries_can_be_filtered_by_point(client, admin, farmer, produce_line, rate):
    home = _point(client, admin, code="KSM-CENTRAL")
    other = _point(client, admin, code="KSM-WEST", name="Kisumu West")
    _deliver(client, admin, farmer, produce_line, "10", point_id=home["id"])
    _deliver(client, admin, farmer, produce_line, "4", point_id=other["id"])

    filtered = client.get(
        "/deliveries",
        params={"collection_point_id": other["id"]},
        headers=_auth(admin),
    )

    assert filtered.json()["total"] == 1
    assert Decimal(filtered.json()["items"][0]["quantity"]) == Decimal("4")


def test_production_by_point_reports_net_quantity_and_value(
    client, admin, farmer, produce_line, rate
):
    """10 kg @ 50 = 500 at one point, 4 kg = 200 at another."""
    home = _point(client, admin, code="KSM-CENTRAL")
    other = _point(client, admin, code="KSM-WEST", name="Kisumu West")
    _deliver(client, admin, farmer, produce_line, "10", point_id=home["id"])
    _deliver(client, admin, farmer, produce_line, "4", point_id=other["id"])

    report = client.get("/reports/production-by-point", headers=_auth(admin))

    assert report.status_code == 200, report.text
    rows = {row["collection_point_code"]: row for row in report.json()["items"]}
    assert Decimal(rows["KSM-CENTRAL"]["quantity"]) == Decimal("10")
    assert Decimal(rows["KSM-CENTRAL"]["value"]) == Decimal("500")
    assert Decimal(rows["KSM-WEST"]["quantity"]) == Decimal("4")
    assert Decimal(rows["KSM-WEST"]["value"]) == Decimal("200")


def test_production_by_point_shows_unassigned_deliveries(
    client, admin, farmer, produce_line, rate
):
    _deliver(client, admin, farmer, produce_line, "7")

    report = client.get("/reports/production-by-point", headers=_auth(admin)).json()

    row = report["items"][0]
    assert row["collection_point_id"] is None
    assert row["collection_point_name"] == "Unassigned"
    assert Decimal(row["quantity"]) == Decimal("7")


def test_reversals_reduce_the_points_net_quantity(
    client, admin, farmer, produce_line, rate
):
    point = _point(client, admin)
    delivery = _deliver(client, admin, farmer, produce_line, "10", point_id=point["id"])
    reversed_ = client.post(
        f"/deliveries/{delivery['id']}/reverse",
        json={"reason": "wet"},
        headers=_auth(admin),
    )
    assert reversed_.status_code == 201, reversed_.text

    report = client.get("/reports/production-by-point", headers=_auth(admin)).json()

    assert Decimal(report["items"][0]["quantity"]) == Decimal("0")
    assert Decimal(report["items"][0]["value"]) == Decimal("0")


def test_the_report_respects_the_date_window(client, admin, farmer, produce_line, rate):
    point = _point(client, admin)
    _deliver(client, admin, farmer, produce_line, "10", point_id=point["id"])

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    future = (date.today() + timedelta(days=1)).isoformat()

    past = client.get(
        "/reports/production-by-point",
        params={"delivered_to": yesterday},
        headers=_auth(admin),
    )
    window = client.get(
        "/reports/production-by-point",
        params={"delivered_from": yesterday, "delivered_to": future},
        headers=_auth(admin),
    )

    # A window with no deliveries returns no rows at all, rather than a row
    # of zeroes for a point that did not trade.
    assert past.json()["items"] == []
    assert Decimal(window.json()["items"][0]["quantity"]) == Decimal("10")
