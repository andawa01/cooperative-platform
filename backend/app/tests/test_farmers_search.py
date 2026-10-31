"""
Farmer search behaviour.

Search is `lower(first_name) LIKE '%q%' OR lower(last_name) LIKE '%q%' OR
phone LIKE '%q%'` (services/farmer.py). The index that serves it is a
trigram GIN, but the behaviour under test is the matching rule: partial,
case-insensitive, across three fields. Changing the predicate without
changing the index would silently drop back to a sequential scan, and these
tests would still pass — that is what migration e52b47e5ff15's EXPLAIN check
covers.
"""

import uuid

from app.core.security import create_access_token
from app.models.farmer import Farmer, FarmerStatus


def _auth_header(user) -> dict:
    tok = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {tok}"}


def _farmer(db, admin, first: str, last: str, phone: str) -> Farmer:
    f = Farmer(
        first_name=first,
        last_name=last,
        phone=phone,
        status=FarmerStatus.ACTIVE.value,
        created_by_id=admin.id,
    )
    db.add(f)
    db.flush()
    return f


def _seed(db, admin):
    return (
        _farmer(
            db,
            admin,
            "Wanjiku",
            "Ochieng",
            f"+2547{uuid.uuid4().int % 10**8:08d}",
        ),
        _farmer(
            db,
            admin,
            "Otieno",
            "Maina",
            f"+2547{uuid.uuid4().int % 10**8:08d}",
        ),
    )


def _search(client, admin, term: str) -> list[dict]:
    r = client.get(f"/farmers?search={term}", headers=_auth_header(admin))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_search_matches_partial_first_name(client, admin, db):
    wanjiku, _ = _seed(db, admin)

    items = _search(client, admin, "wanj")
    assert [f["id"] for f in items] == [str(wanjiku.id)]


def test_search_matches_last_name_case_insensitively(client, admin, db):
    _, otieno = _seed(db, admin)

    items = _search(client, admin, "MAINA")
    assert [f["id"] for f in items] == [str(otieno.id)]


def test_search_matches_phone_fragment(client, admin, db):
    wanjiku, _ = _seed(db, admin)

    fragment = wanjiku.phone[-5:]
    ids = {f["id"] for f in _search(client, admin, fragment)}
    assert str(wanjiku.id) in ids


def test_search_with_no_match_returns_empty(client, admin, db):
    _seed(db, admin)
    assert _search(client, admin, "zzz-nobody") == []
