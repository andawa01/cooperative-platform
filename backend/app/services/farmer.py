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
import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.farmer import Farmer, FarmerStatus
from app.models.user import User
from app.schemas.farmer import FarmerCreate, FarmerUpdate


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

    farmer = Farmer(
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        phone=normalized_phone,
        date_of_birth=data.date_of_birth,
        national_id=(data.national_id.strip() if data.national_id else None),
        location=(data.location.strip() if data.location else None),
        notes=data.notes,
        status=FarmerStatus.PENDING_VERIFICATION.value,
        created_by_id=actor.id,
    )

    db.add(farmer)
    try:
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
) -> Farmer:
    """
    Apply a partial update. Only fields actually present in the request
    (via exclude_unset) are applied.
    """
    farmer = get_farmer(db, farmer_id)

    updates = data.model_dump(exclude_unset=True)

    # Defensive: even though the schema excludes these, keep the service
    # honest in case the schema is ever loosened.
    forbidden = {"phone", "status", "merged_into_id", "created_by_id"}
    leaked = forbidden & set(updates)
    if leaked:
        raise ValueError(f"fields not patchable via this method: {leaked}")

    for key, value in updates.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(farmer, key, value)

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
    from datetime import datetime, timezone

    farmer = get_farmer(db, farmer_id)

    if farmer.status == FarmerStatus.MERGED.value:
        raise FarmerNotMergeable("cannot verify a merged farmer")

    if farmer.verified_at is None:
        farmer.verified_at = datetime.now(timezone.utc)
        farmer.verified_by_id = actor.id
        if farmer.status == FarmerStatus.PENDING_VERIFICATION.value:
            farmer.status = FarmerStatus.ACTIVE.value
        db.commit()
        db.refresh(farmer)

    return farmer


def archive_farmer(
    db: Session,
    farmer_id: uuid.UUID,
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
        farmer.status = FarmerStatus.ARCHIVED.value
        if reason:
            existing = farmer.notes or ""
            farmer.notes = f"{existing}\n[archived] {reason}".strip()
        db.commit()
        db.refresh(farmer)

    return farmer