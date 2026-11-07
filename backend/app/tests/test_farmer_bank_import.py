"""
Bulk bank details import (D-037).

These hold the import to its promise: a preview writes nothing, an apply
writes only rows that matched a member with a usable pair, and every skipped
row says which line it was and why. An import that reports "3 applied" while
silently dropping 40 rows is worse than no import at all.
"""

import uuid

from app.core.security import create_access_token

HEADER = "phone,bank_name,bank_account_number\n"


def _auth(user) -> dict:
    token = create_access_token(str(user.id), role=user.role)
    return {"Authorization": f"Bearer {token}"}


def _import(client, user, csv_text: str, *, dry_run: bool = True):
    return client.post(
        "/farmers/bank-details/import",
        json={"csv": csv_text, "dry_run": dry_run},
        headers=_auth(user),
    )


def test_preview_reports_matches_and_writes_nothing(client, admin, farmer):
    r = _import(client, admin, HEADER + f"{farmer.phone},KCB,0123456789\n")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["valid"] == 1
    assert body["applied"] == 0
    assert body["rows"][0]["farmer_name"] == "Test Farmer"

    after = client.get(f"/farmers/{farmer.id}", headers=_auth(admin))
    assert after.json()["bank_name"] is None


def test_apply_writes_the_valid_rows(client, admin, farmer):
    # Excel writes a BOM; the first header cell must still read as `phone`.
    r = _import(
        client,
        admin,
        "\ufeff" + HEADER + f"{farmer.phone},KCB,0123456789\n",
        dry_run=False,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] == 1
    assert body["rows"][0]["status"] == "applied"

    after = client.get(f"/farmers/{farmer.id}", headers=_auth(admin))
    assert after.json()["bank_name"] == "KCB"
    assert after.json()["bank_account_number"] == "0123456789"


def test_local_phone_format_matches_the_member(client, admin, farmer):
    """The treasurer's sheet has 07… numbers, not E.164."""
    local = "0" + farmer.phone[4:]

    r = _import(client, admin, HEADER + f"{local},Equity,1234567890\n")

    assert r.status_code == 200, r.text
    assert r.json()["valid"] == 1


def test_unknown_phone_is_reported_and_others_still_apply(client, admin, farmer):
    r = _import(
        client,
        admin,
        HEADER
        + f"{farmer.phone},KCB,0123456789\n"
        + "+254700000000,Equity,1234567890\n",
        dry_run=False,
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] == 1
    assert body["errors"] == 1
    unknown = [row for row in body["rows"] if row["status"] == "error"][0]
    assert unknown["line"] == 3
    assert "No member has this phone number." in unknown["message"]


def test_bad_account_number_is_reported(client, admin, farmer):
    r = _import(client, admin, HEADER + f"{farmer.phone},KCB,12AB567\n")

    assert r.status_code == 200, r.text
    row = r.json()["rows"][0]
    assert row["status"] == "error"
    assert "6–20 digits" in row["message"]


def test_missing_bank_name_is_reported(client, admin, farmer):
    r = _import(client, admin, HEADER + f"{farmer.phone},,0123456789\n")

    row = r.json()["rows"][0]
    assert row["status"] == "error"
    assert "Bank name is required" in row["message"]


def test_duplicate_phone_in_the_file_is_reported(client, admin, farmer):
    r = _import(
        client,
        admin,
        HEADER
        + f"{farmer.phone},KCB,0123456789\n"
        + f"{farmer.phone},Equity,9999999999\n",
        dry_run=False,
    )

    body = r.json()
    assert body["applied"] == 1
    duplicate = [row for row in body["rows"] if row["line"] == 3][0]
    assert duplicate["status"] == "error"
    assert "line 2" in duplicate["message"]
    # The first row wins; the second did not overwrite it.
    after = client.get(f"/farmers/{farmer.id}", headers=_auth(admin))
    assert after.json()["bank_name"] == "KCB"


def test_missing_headers_is_rejected(client, admin):
    r = _import(client, admin, "phone,account\n254712345678,1234567890\n")

    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "bank_name" in detail
    assert "bank_account_number" in detail


def test_empty_file_is_rejected(client, admin):
    r = _import(client, admin, HEADER)

    assert r.status_code == 422
    assert "no members" in r.json()["detail"]


def test_clerk_cannot_import(client, clerk, farmer):
    r = _import(client, clerk, HEADER + f"{farmer.phone},KCB,0123456789\n")

    assert r.status_code == 403


def test_overflow_phone_column_is_reported(client, admin):
    """A row shorter than the header is an error, not a crash."""
    r = _import(client, admin, HEADER + f"{uuid.uuid4().hex}\n")

    assert r.status_code == 200, r.text
    assert r.json()["rows"][0]["status"] == "error"
