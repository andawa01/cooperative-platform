"""
Farmer service — business logic for farmer registration and lifecycle.

Conventions:
- Functions raise domain exceptions (defined here) for business rule
  violations. Routers translate those into HTTP.
- Functions operate on `Session` (sync). Transactions are explicit where
  they matter (create, update, status transitions). Plain reads are not
  wrapped.
- The service normalizes `phone` (E.164) per DECISIONS.md D-016.
"""

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.farmer import Farmer, FarmerStatus
from app.models.user import User
from app.schemas.farmer import FarmerCreate, FarmerUpdate
from app.services import audit
from app.services.collection_point import resolve_active_point

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class FarmerNotFound(Exception):
    """Raised when a farmer id does not exist."""


class FarmerPhoneTaken(Exception):
    """Raised on unique-constraint violation for phone."""


class FarmerNationalIdTaken(Exception):
    """Raised on unique-constraint violation for national_id."""


class InvalidPhoneFormat(Exception):
    """Raised when a phone cannot be normalized to E.164."""


class IncompleteBankDetails(Exception):
    """Bank name and account number must be set together (D-036)."""


class InvalidBankImport(Exception):
    """The uploaded file cannot be read as a bank-details CSV (D-037)."""


class FarmerNotMergeable(Exception):
    """Raised when attempting to merge in an invalid state."""


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------

_E164_RE = re.compile(r"^\+[1-9][0-9]{6,14}$")

# We support a small set of common local formats per country. Extending this
# is trivial — add a new (prefix -> country_code) entry. See D-016.
_LOCAL_PREFIXES = {
    # Kenya: 07XXXXXXXX and 01XXXXXXXX are 10-digit national numbers.
    # A leading 0 is replaced with +254, then the remaining 9 digits.
    "KE": {
        "local_pattern": re.compile(r"^0([17][0-9]{8})$"),
        "country_code": "+254",
    },
}


def normalize_phone(raw: str, country: str = "KE") -> str:
    """
    Convert a phone string to E.164 or raise InvalidPhoneFormat.

    Accepted inputs:
      - Already E.164:  '+254712345678'  → returned as-is
      - Kenyan local:   '0712345678'     → '+254712345678'
      - Kenyan local:   '0112345678'     → '+254112345678'  (new 011 range)

    Rejected:
      - Anything else. The API rejects unknown formats rather than guessing.

    The `country` parameter is deliberate. It defaults to KE (our seed
    context) but is a per-request decision we could later derive from the
    authenticated user's cooperative. See D-016.
    """
    if raw is None:
        raise InvalidPhoneFormat("phone is required")

    value = raw.strip()

    # Already E.164? Return canonical form.
    if _E164_RE.match(value):
        return value

    cfg = _LOCAL_PREFIXES.get(country)
    if cfg:
        m = cfg["local_pattern"].match(value)
        if m:
            return f"{cfg['country_code']}{m.group(1)}"

    raise InvalidPhoneFormat(
        f"phone '{raw}' is not E.164 and does not match a known local format"
    )


# ---------------------------------------------------------------------------
# Create / read
# ---------------------------------------------------------------------------


def create_farmer(
    db: Session,
    data: FarmerCreate,
    actor: User,
) -> Farmer:
    """
    Register a new farmer.

    - Normalizes phone to E.164.
    - Enforces uniqueness on phone and national_id at the DB level;
      IntegrityError is translated into a domain exception.
    - Sets status to PENDING_VERIFICATION.
    - Records created_by_id = actor.id (audit).
    """
    normalized_phone = normalize_phone(data.phone)

    # A point that does not exist or has been retired cannot become a
    # member's home; the error is raised before anything is written (D-039).
    if data.collection_point_id is not None:
        resolve_active_point(db, data.collection_point_id)

    farmer = Farmer(
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        phone=normalized_phone,
        date_of_birth=data.date_of_birth,
        national_id=(data.national_id.strip() if data.national_id else None),
        bank_name=(data.bank_name.strip() if data.bank_name else None),
        bank_account_number=(
            data.bank_account_number.strip() if data.bank_account_number else None
        ),
        collection_point_id=data.collection_point_id,
        location=(data.location.strip() if data.location else None),
        notes=data.notes,
        status=FarmerStatus.PENDING_VERIFICATION.value,
        created_by_id=actor.id,
    )

    db.add(farmer)
    try:
        db.flush()  # assign the id the audit entry references
        audit.record(
            db,
            actor_id=actor.id,
            action="farmer.create",
            entity_type="farmer",
            entity_id=farmer.id,
            after={
                "first_name": farmer.first_name,
                "last_name": farmer.last_name,
                "phone": farmer.phone,
                "national_id": farmer.national_id,
                "bank_name": farmer.bank_name,
                "bank_account_number": farmer.bank_account_number,
                "collection_point_id": (
                    str(farmer.collection_point_id)
                    if farmer.collection_point_id
                    else None
                ),
                "status": farmer.status,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        msg = str(exc.orig).lower()
        if "uq_farmer_phone" in msg or "farmer_phone" in msg:
            raise FarmerPhoneTaken() from exc
        if "uq_farmer_national_id" in msg or "farmer_national_id" in msg:
            raise FarmerNationalIdTaken() from exc
        raise
    db.refresh(farmer)
    return farmer


def get_farmer(db: Session, farmer_id: uuid.UUID) -> Farmer:
    farmer = db.get(Farmer, farmer_id)
    if farmer is None:
        raise FarmerNotFound()
    return farmer


def list_farmers(
    db: Session,
    *,
    status: FarmerStatus | None = None,
    search: str | None = None,
    include_merged: bool = False,
    collection_point_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Farmer], int]:
    """
    List farmers with filters and pagination.

    Default behavior (include_merged=False) excludes merged farmers, because
    they are historical artifacts. Callers can override to include them.

    `search` matches a case-insensitive substring of first_name, last_name,
    or phone.

    Returns (items, total_count). The total is the count BEFORE limit/offset,
    so clients can render pagination correctly.
    """
    stmt = select(Farmer)
    count_stmt = select(func.count()).select_from(Farmer)

    conditions = []
    if status is not None:
        conditions.append(Farmer.status == status.value)
    elif not include_merged:
        conditions.append(Farmer.status != FarmerStatus.MERGED.value)

    if collection_point_id is not None:
        conditions.append(Farmer.collection_point_id == collection_point_id)

    if search:
        pattern = f"%{search.strip().lower()}%"
        conditions.append(
            or_(
                func.lower(Farmer.first_name).like(pattern),
                func.lower(Farmer.last_name).like(pattern),
                Farmer.phone.like(f"%{search.strip()}%"),
            )
        )

    for c in conditions:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    stmt = stmt.order_by(Farmer.created_at.desc()).limit(limit).offset(offset)

    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt).all())
    return items, total


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def update_farmer(
    db: Session,
    farmer_id: uuid.UUID,
    data: FarmerUpdate,
    actor: User,
) -> Farmer:
    """
    Apply a partial update. Only fields actually present in the request
    (via exclude_unset) are applied.

    Records exactly the fields that changed — a PATCH that changes nothing
    writes no audit row, because nothing happened.
    """
    farmer = get_farmer(db, farmer_id)

    updates = data.model_dump(exclude_unset=True)

    if updates.get("collection_point_id") is not None:
        resolve_active_point(db, updates["collection_point_id"])

    # Defensive: even though the schema excludes these, keep the service
    # honest in case the schema is ever loosened.
    forbidden = {"phone", "status", "merged_into_id", "created_by_id"}
    leaked = forbidden & set(updates)
    if leaked:
        raise ValueError(f"fields not patchable via this method: {leaked}")

    before: dict = {}
    after: dict = {}
    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip() or None
        previous = getattr(farmer, key)
        if previous == value:
            continue
        before[key] = audit.snapshot(previous)
        after[key] = audit.snapshot(value)
        setattr(farmer, key, value)

    # A PATCH can clear or set one half of the pair on its own (e.g. a client
    # that only knows about account numbers). The stored row must never end up
    # with half a destination, so check the resulting row, not the payload.
    if (farmer.bank_name is None) != (farmer.bank_account_number is None):
        db.rollback()
        raise IncompleteBankDetails()

    if before:
        audit.record(
            db,
            actor_id=actor.id,
            action="farmer.update",
            entity_type="farmer",
            entity_id=farmer.id,
            before=before,
            after=after,
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        msg = str(exc.orig).lower()
        if "uq_farmer_national_id" in msg or "farmer_national_id" in msg:
            raise FarmerNationalIdTaken() from exc
        raise
    db.refresh(farmer)
    return farmer


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def verify_farmer(
    db: Session,
    farmer_id: uuid.UUID,
    actor: User,
) -> Farmer:
    """
    Mark a farmer as verified. Only valid from PENDING_VERIFICATION.
    Idempotency: verifying an already-verified farmer is a no-op, not an error.
    """
    from datetime import datetime

    farmer = get_farmer(db, farmer_id)

    if farmer.status == FarmerStatus.MERGED.value:
        raise FarmerNotMergeable("cannot verify a merged farmer")

    if farmer.verified_at is None:
        previous_status = farmer.status
        farmer.verified_at = datetime.now(UTC)
        farmer.verified_by_id = actor.id
        if farmer.status == FarmerStatus.PENDING_VERIFICATION.value:
            farmer.status = FarmerStatus.ACTIVE.value
        audit.record(
            db,
            actor_id=actor.id,
            action="farmer.verify",
            entity_type="farmer",
            entity_id=farmer.id,
            before={"status": previous_status, "verified_at": None},
            after={
                "status": farmer.status,
                "verified_at": farmer.verified_at.isoformat(),
                "verified_by_id": str(actor.id),
            },
        )
        db.commit()
        db.refresh(farmer)

    return farmer


def archive_farmer(
    db: Session,
    farmer_id: uuid.UUID,
    actor: User,
    reason: str | None = None,
) -> Farmer:
    """
    Archive a farmer. Historical deliveries and payments remain.
    Archived farmers cannot receive new deliveries (enforced at the delivery
    service, not here).

    Idempotency: archiving an already-archived farmer is a no-op.
    """
    farmer = get_farmer(db, farmer_id)

    if farmer.status == FarmerStatus.MERGED.value:
        raise FarmerNotMergeable("cannot archive a merged farmer")

    if farmer.status != FarmerStatus.ARCHIVED.value:
        previous_status = farmer.status
        farmer.status = FarmerStatus.ARCHIVED.value
        if reason:
            existing = farmer.notes or ""
            farmer.notes = f"{existing}\n[archived] {reason}".strip()
        audit.record(
            db,
            actor_id=actor.id,
            action="farmer.archive",
            entity_type="farmer",
            entity_id=farmer.id,
            before={"status": previous_status},
            after={"status": farmer.status, "reason": reason},
        )
        db.commit()
        db.refresh(farmer)

    return farmer


# ---------------------------------------------------------------------------
# Bulk bank details (D-037)
# ---------------------------------------------------------------------------

MAX_IMPORT_ROWS = 500

IMPORT_COLUMNS = ("phone", "bank_name", "bank_account_number")

_BANK_ACCOUNT_RE = re.compile(r"^[0-9]{6,20}$")


@dataclass
class BankImportRow:
    line: int
    phone: str
    farmer_name: str | None
    status: str
    message: str | None


@dataclass
class BankImportResult:
    dry_run: bool
    total: int
    valid: int
    applied: int
    errors: int
    rows: list[BankImportRow]


def _read_bank_csv(text: str) -> list[tuple[int, dict[str, str]]]:
    """
    Parse and range-check the file.

    A bad file is an error, not "0 members matched": a header typo reported as
    an empty import is how someone silently re-uploads the same wrong file
    three times. The BOM is stripped because Excel writes one, and the first
    column header would otherwise arrive as `\ufeffphone`.
    """
    text = text.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(text, newline=""))

    try:
        raw_header = next(reader)
    except StopIteration:
        raise InvalidBankImport(
            "The file is empty. It needs a header row: "
            "phone, bank_name, bank_account_number."
        ) from None

    header = [cell.strip().lower().replace(" ", "_") for cell in raw_header]
    missing = [column for column in IMPORT_COLUMNS if column not in header]
    if missing:
        raise InvalidBankImport(
            "The header row is missing "
            + ", ".join(missing)
            + ". Expected: phone, bank_name, bank_account_number."
        )

    index = {column: header.index(column) for column in IMPORT_COLUMNS}

    rows: list[tuple[int, dict[str, str]]] = []
    for line, cells in enumerate(reader, start=2):
        if not any(cell.strip() for cell in cells):
            continue
        rows.append(
            (
                line,
                {
                    column: (cells[i].strip() if i < len(cells) else "")
                    for column, i in index.items()
                },
            )
        )

    if not rows:
        raise InvalidBankImport("The file has a header but no members in it.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise InvalidBankImport(
            f"The file has {len(rows)} rows; the limit is {MAX_IMPORT_ROWS} per "
            "import. Split it into smaller files."
        )
    return rows


def import_bank_details(
    db: Session,
    csv_text: str,
    actor: User,
    *,
    dry_run: bool = True,
) -> BankImportResult:
    """
    Add or correct bank details for many members in one file.

    Preview by default: every row is checked and reported, but nothing is
    written. Applying writes only the valid rows and records the same
    `farmer.update` audit entry a manual edit would, so the trail does not
    depend on how the change arrived.

    Matching is by phone, because the phone is the member's unique handle and
    the field a treasurer's spreadsheet already has. Every failure names the
    line it came from: "nothing happened" is only useful if the admin knows
    which of 200 rows to fix. Rows are never created — an unknown phone is a
    typo or a member who was never registered, and guessing is not an option
    for a payout destination.
    """
    parsed = _read_bank_csv(csv_text)

    # Normalise every phone first, so the member lookup is one query rather
    # than one per row (D-027).
    candidates: list[tuple[int, dict[str, str], str | None, str | None]] = []
    phones: set[str] = set()
    for line, record in parsed:
        phone: str | None = None
        error: str | None = None
        raw_phone = record["phone"]
        if not raw_phone:
            error = "Phone is required to find the member."
        else:
            try:
                phone = normalize_phone(raw_phone)
                phones.add(phone)
            except InvalidPhoneFormat as exc:
                error = str(exc)
        candidates.append((line, record, phone, error))

    farmers = (
        {
            farmer.phone: farmer
            for farmer in db.scalars(select(Farmer).where(Farmer.phone.in_(phones)))
        }
        if phones
        else {}
    )

    rows: list[BankImportRow] = []
    valid: list[tuple[BankImportRow, Farmer, str, str]] = []
    seen: dict[str, int] = {}

    for line, record, phone, error in candidates:
        if error is not None or phone is None:
            rows.append(
                BankImportRow(line, phone or record["phone"], None, "error", error)
            )
            continue

        if phone in seen:
            rows.append(
                BankImportRow(
                    line,
                    phone,
                    None,
                    "error",
                    f"This phone already appears on line {seen[phone]}.",
                )
            )
            continue
        seen[phone] = line

        farmer = farmers.get(phone)
        if farmer is None:
            rows.append(
                BankImportRow(
                    line, phone, None, "error", "No member has this phone number."
                )
            )
            continue

        bank_name = record["bank_name"]
        account = record["bank_account_number"].replace(" ", "")
        if not bank_name:
            error = "Bank name is required alongside the account number."
        elif not _BANK_ACCOUNT_RE.match(account):
            error = "Account number must be 6–20 digits."

        if error is not None:
            rows.append(BankImportRow(line, phone, farmer.full_name, "error", error))
            continue

        row = BankImportRow(line, phone, farmer.full_name, "valid", None)
        rows.append(row)
        valid.append((row, farmer, bank_name[:100], account))

    applied = 0
    if not dry_run:
        for row, farmer, bank_name, account in valid:
            if farmer.bank_name == bank_name and farmer.bank_account_number == account:
                row.status = "applied"
                applied += 1
                continue
            audit.record(
                db,
                actor_id=actor.id,
                action="farmer.update",
                entity_type="farmer",
                entity_id=farmer.id,
                before={
                    "bank_name": farmer.bank_name,
                    "bank_account_number": farmer.bank_account_number,
                },
                after={"bank_name": bank_name, "bank_account_number": account},
            )
            farmer.bank_name = bank_name
            farmer.bank_account_number = account
            row.status = "applied"
            applied += 1
        db.commit()

    return BankImportResult(
        dry_run=dry_run,
        total=len(rows),
        valid=sum(1 for row in rows if row.status in {"valid", "applied"}),
        applied=applied,
        errors=sum(1 for row in rows if row.status == "error"),
        rows=rows,
    )
