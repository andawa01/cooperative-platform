"""
ShambaTrack seed data.

Idempotent by default: refuses to run if the database already has users.
Pass --reset to wipe everything and start over.

Usage:
    python -m scripts.seed              # fresh DB only
    python -m scripts.seed --reset      # wipe and re-seed

Design:
- Deterministic. All randomness flows from a fixed seed, so re-running
  produces the same data.
- Reference data (users, produce lines, rates) inserted directly via the
  ORM. The business rules for these are minimal and not worth exercising
  through the service layer.
- Business data (farmers, deliveries, payments) inserted via the service
  layer, so the seed exercises the same code paths as production.
- Deliberately includes edge cases for demos:
    * pending, suspended, archived farmers (not just active ones)
    * a produce line with no rate, creating pending-valuation deliveries
    * an advance payment with unallocated credit
    * one delivery reversal and one payment reversal
- Refuses to run against a non-empty database unless --reset is passed,
  because it deletes everything.

The session handling here is deliberate. Our services call db.refresh()
after committing, which leaves an autobegun transaction open on the session.
The next service call finds a transaction already in progress and uses a
savepoint — the writes are real, but the outer transaction stays open. To
make each step independent, we explicitly commit after every service call.
"""

import argparse
import random
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.farmer import Farmer, FarmerStatus
from app.models.produce import ProduceLine, Rate
from app.models.user import User, UserRole
from app.schemas.delivery import DeliveryCreate
from app.schemas.farmer import FarmerCreate
from app.schemas.payment import PaymentCreate
from app.services import delivery as delivery_service
from app.services import farmer as farmer_service
from app.services import payment as payment_service

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RNG = random.Random(42)

# Demo credentials — printed at the end.
ADMIN_EMAIL = "admin@shambatrack.io"
ADMIN_PASSWORD = "demo-admin-123"
CLERK_EMAILS = [
    "clerk1@shambatrack.io",
    "clerk2@shambatrack.io",
    "clerk3@shambatrack.io",
]
CLERK_PASSWORD = "demo-clerk-123"

# 30 farmers is enough for a realistic demo and keeps the seed fast.
N_FARMERS = 30
N_DELIVERIES = 150
N_PAYMENTS = 12

FIRST_NAMES = [
    "Kamau",
    "Otieno",
    "Wanjiru",
    "Mwangi",
    "Achieng",
    "Kipchoge",
    "Nyokabi",
    "Omondi",
    "Wafula",
    "Cheruiyot",
    "Wanjiku",
    "Akinyi",
    "Nyambura",
    "Adhiambo",
    "Chebet",
    "Nafula",
    "Muthoni",
    "Wairimu",
    "Jerono",
    "Atieno",
]
LAST_NAMES = [
    "Kimani",
    "Ochieng",
    "Mutua",
    "Karanja",
    "Njoroge",
    "Wekesa",
    "Barasa",
    "Kiprono",
    "Odhiambo",
    "Muthama",
    "Waweru",
    "Kilonzo",
    "Maina",
    "Owuor",
    "Kibet",
]


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


def _reset(session) -> None:
    """
    Delete every row, in an order that respects FK RESTRICT constraints.

    Self-references (reversal_of_id, merged_into_id) are nulled first, so
    we don't need to worry about deletion order within a table.
    """
    print("Wiping existing data...", end=" ", flush=True)
    session.execute(text("UPDATE payments SET reversal_of_id = NULL"))
    session.execute(text("UPDATE payment_allocations SET reversal_of_id = NULL"))
    session.execute(text("UPDATE deliveries SET reversal_of_id = NULL"))
    session.execute(text("UPDATE farmers SET merged_into_id = NULL"))
    session.execute(text("UPDATE farmers SET verified_by_id = NULL"))
    session.commit()

    for table in [
        "payment_allocations",
        "payments",
        "deliveries",
        "rates",
        "produce_lines",
        "farmers",
        "users",
    ]:
        session.execute(text(f"DELETE FROM {table}"))
    session.commit()
    print("done")


# ---------------------------------------------------------------------------
# Reference data (direct ORM)
# ---------------------------------------------------------------------------


def _create_users(session) -> tuple[User, list[User]]:
    print("Creating users...", end=" ", flush=True)
    admin = User(
        email=ADMIN_EMAIL,
        full_name="Alice Admin",
        hashed_password=hash_password(ADMIN_PASSWORD),
        role=UserRole.ADMIN.value,
        is_active=True,
    )
    session.add(admin)
    session.flush()

    clerks = []
    for i, email in enumerate(CLERK_EMAILS, start=1):
        clerk = User(
            email=email,
            full_name=f"Clerk {i}",
            hashed_password=hash_password(CLERK_PASSWORD),
            role=UserRole.CLERK.value,
            is_active=True,
        )
        session.add(clerk)
        clerks.append(clerk)

    session.commit()
    print(f"{1 + len(clerks)} created")
    return admin, clerks


def _create_produce_lines(session, admin: User) -> dict[str, ProduceLine]:
    print("Creating produce lines...", end=" ", flush=True)
    lines = {}
    for code, name, unit in [
        ("coffee", "Coffee", "kg"),
        ("tea", "Tea", "kg"),
        ("dairy", "Dairy", "liter"),
        # Banana is deliberately left without a rate so it can be used to
        # demo the pending-valuation workflow.
        ("banana", "Banana", "kg"),
    ]:
        line = ProduceLine(
            code=code,
            name=name,
            unit=unit,
            is_active=True,
            created_by_id=admin.id,
        )
        session.add(line)
        lines[code] = line
    session.commit()
    print(f"{len(lines)} created")
    return lines


def _create_rates(session, admin: User, lines: dict[str, ProduceLine]) -> None:
    print("Creating rates...", end=" ", flush=True)
    # Two rates per line (except banana): historical and current.
    schedule = {
        "coffee": [
            (date(2024, 1, 1), Decimal("45.0000")),
            (date(2025, 1, 1), Decimal("50.0000")),
        ],
        "tea": [
            (date(2024, 1, 1), Decimal("30.0000")),
            (date(2025, 1, 1), Decimal("35.0000")),
        ],
        "dairy": [
            (date(2024, 1, 1), Decimal("40.0000")),
            (date(2025, 1, 1), Decimal("42.0000")),
        ],
    }
    count = 0
    for code, entries in schedule.items():
        line = lines[code]
        for i, (eff_from, rate) in enumerate(entries):
            is_last = i == len(entries) - 1
            eff_to = None if is_last else entries[i + 1][0]
            session.add(
                Rate(
                    produce_line_id=line.id,
                    rate_per_unit=rate,
                    currency="KES",
                    effective_from=eff_from,
                    effective_to=eff_to,
                    created_by_id=admin.id,
                )
            )
            count += 1
    session.commit()
    print(f"{count} created")


# ---------------------------------------------------------------------------
# Farmers (via service)
# ---------------------------------------------------------------------------


def _create_farmers(session, admin: User, clerk: User) -> list[Farmer]:
    print(f"Creating {N_FARMERS} farmers...", end=" ", flush=True)
    farmers: list[Farmer] = []
    for i in range(N_FARMERS):
        first = RNG.choice(FIRST_NAMES)
        last = RNG.choice(LAST_NAMES)
        # National ID present on ~70%, absent on the rest — matches reality.
        has_nid = RNG.random() < 0.7
        data = FarmerCreate(
            first_name=first,
            last_name=last,
            phone=f"+2547{i:08d}",
            national_id=f"KE{RNG.randint(10000000, 99999999)}" if has_nid else None,
            location=RNG.choice(
                [
                    "Kisumu Central",
                    "Kisumu East",
                    "Nandi Hills",
                    "Kapsabet",
                    "Kericho",
                    "Nakuru",
                    None,
                ]
            ),
        )
        try:
            farmer = farmer_service.create_farmer(session, data, clerk)
            session.commit()
            farmers.append(farmer)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            print(f"\n  ! farmer {i} failed: {exc}")
    print(f"{len(farmers)} created")
    return farmers


def _verify_farmers(session, admin: User, farmers: list[Farmer]) -> None:
    print("Verifying farmers...", end=" ", flush=True)
    # Activate most; leave a few in each non-active state.
    n_pending = 3
    n_suspended = 2
    n_archived = 1
    cutoff = len(farmers) - n_pending - n_suspended - n_archived

    verified = 0
    for i, farmer in enumerate(farmers):
        if i < cutoff:
            farmer_service.verify_farmer(session, farmer.id, admin)
            session.commit()
            verified += 1
        elif i < cutoff + n_suspended:
            farmer.status = FarmerStatus.SUSPENDED.value
        elif i < cutoff + n_suspended + n_archived:
            farmer.status = FarmerStatus.ARCHIVED.value
        # The remainder stay pending_verification.
    session.commit()
    print(
        f"{verified} verified, {n_pending} pending, "
        f"{n_suspended} suspended, {n_archived} archived"
    )


# ---------------------------------------------------------------------------
# Deliveries (via service)
# ---------------------------------------------------------------------------


def _create_deliveries(
    session,
    admin: User,
    clerk: User,
    farmers: list[Farmer],
    lines: dict[str, ProduceLine],
) -> list:
    print(f"Recording {N_DELIVERIES} deliveries...", end=" ", flush=True)

    # Only active, non-archived farmers receive deliveries.
    active = [f for f in farmers if f.status == FarmerStatus.ACTIVE.value]
    # Active lines that have rates, plus banana (no rate → unvalued).
    rate_lines = ["coffee", "tea", "dairy"]
    unvalued_line = "banana"

    # Deliveries spread over the past 180 days.
    now = datetime.now(UTC)

    created = []
    for i in range(N_DELIVERIES):
        farmer = RNG.choice(active)
        # 5 of the N are against banana (unvalued).
        code = unvalued_line if i % 30 == 0 else RNG.choice(rate_lines)
        line = lines[code]
        quantity = Decimal(f"{RNG.uniform(5, 150):.4f}")
        days_ago = RNG.randint(0, 180)
        delivered_at = now - timedelta(days=days_ago, hours=RNG.randint(0, 10))

        try:
            d = delivery_service.record_delivery(
                session,
                DeliveryCreate(
                    farmer_id=farmer.id,
                    produce_line_id=line.id,
                    quantity=quantity,
                    delivered_at=delivered_at,
                    location=farmer.location,
                ),
                clerk,
            )
            session.commit()
            created.append(d)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            print(f"\n  ! delivery {i} failed: {exc}")

    print(f"{len(created)} recorded")
    return created


# ---------------------------------------------------------------------------
# Payments (via service)
# ---------------------------------------------------------------------------


def _create_payments(
    session,
    admin: User,
    farmers: list[Farmer],
) -> list:
    print(f"Recording {N_PAYMENTS} payments...", end=" ", flush=True)
    active = [f for f in farmers if f.status == FarmerStatus.ACTIVE.value]

    now = datetime.now(UTC)
    created = []
    for i in range(N_PAYMENTS):
        farmer = RNG.choice(active)
        # First payment: small FIFO. Second: bigger FIFO (leaves credit).
        # Third: manual allocation. Rest: random FIFO.
        amount = Decimal(f"{RNG.uniform(500, 5000):.4f}")
        paid_at = now - timedelta(days=RNG.randint(0, 90))

        try:
            p, _ = payment_service.record_payment(
                session,
                PaymentCreate(
                    farmer_id=farmer.id,
                    amount=amount,
                    currency="KES",
                    method=RNG.choice(["cash", "mobile_money", "bank_transfer"]),
                    reference=f"MPESA-{RNG.randint(100000, 999999)}"
                    if RNG.random() < 0.6
                    else None,
                    paid_at=paid_at,
                    idempotency_key=f"seed-{i:04d}",
                ),
                admin,
            )
            session.commit()
            created.append(p)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            print(f"\n  ! payment {i} failed: {exc}")

    print(f"{len(created)} recorded")
    return created


def _create_one_advance_payment(session, admin: User, farmers: list[Farmer]) -> None:
    """
    One deliberately oversized payment, to demo available credit.
    """
    print("Creating one advance payment...", end=" ", flush=True)
    active = [f for f in farmers if f.status == FarmerStatus.ACTIVE.value]
    farmer = active[0]
    now = datetime.now(UTC)
    try:
        payment_service.record_payment(
            session,
            PaymentCreate(
                farmer_id=farmer.id,
                amount=Decimal("50000.0000"),
                currency="KES",
                method="bank_transfer",
                reference="ADVANCE-001",
                paid_at=now,
                idempotency_key="seed-advance-001",
            ),
            admin,
        )
        session.commit()
        print("done")
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        print(f"failed: {exc}")


# ---------------------------------------------------------------------------
# Reversals (via service)
# ---------------------------------------------------------------------------


def _create_reversals(session, admin: User, deliveries, payments) -> None:
    print("Creating reversals...", end=" ", flush=True)
    created = 0

    # One delivery reversal (the most recent delivery).
    if deliveries:
        try:
            delivery_service.reverse_delivery(
                session,
                deliveries[-1].id,
                "quantity was recorded incorrectly at the collection point",
                admin,
            )
            session.commit()
            created += 1
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            print(f"\n  ! delivery reversal failed: {exc}")

    # One payment reversal (the oldest payment).
    if payments:
        try:
            payment_service.reverse_payment(
                session,
                payments[0].id,
                "bank returned the transfer",
                admin,
            )
            session.commit()
            created += 1
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            print(f"\n  ! payment reversal failed: {exc}")

    print(f"{created} created")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the ShambaTrack database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe all data before seeding. Required if the DB is not empty.",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        existing_users = session.query(User).count()
        if existing_users > 0 and not args.reset:
            print(
                f"Database already has {existing_users} user(s). "
                f"Refusing to seed.\n"
                f"Pass --reset to wipe and re-seed."
            )
            return 1

        if args.reset:
            _reset(session)

        admin, clerks = _create_users(session)
        lines = _create_produce_lines(session, admin)
        _create_rates(session, admin, lines)
        farmers = _create_farmers(session, admin, clerks[0])
        _verify_farmers(session, admin, farmers)
        deliveries = _create_deliveries(session, admin, clerks[0], farmers, lines)
        payments = _create_payments(session, admin, farmers)
        _create_one_advance_payment(session, admin, farmers)
        _create_reversals(session, admin, deliveries, payments)

        print()
        print("Seed complete.")
        print()
        print("Demo credentials:")
        print(f"  Admin:  {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        for e in CLERK_EMAILS:
            print(f"  Clerk:  {e} / {CLERK_PASSWORD}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
