"""
Auth service — registration and login logic.

Layering: this module does not import FastAPI. It returns domain objects or
raises domain errors. The router translates those into HTTP responses.
"""
import logging

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest


log = logging.getLogger(__name__)


class EmailAlreadyRegistered(Exception):
    """Raised when attempting to register an email that already exists."""


# A pre-computed Argon2 hash used ONLY as a timing decoy.
# When login is attempted for a non-existent email, we verify against this
# dummy so the response time is the same as for a wrong password. Without
# this, an attacker can time the login endpoint to determine which emails
# are registered. See authenticate() below.
_DUMMY_HASH = hash_password("this-is-never-a-real-password")


# Advisory lock key used for the bootstrap operation. Arbitrary but constant —
# every process that wants to bootstrap takes this same lock.
_BOOTSTRAP_LOCK_KEY = 8675309


def create_user(db: Session, data: RegisterRequest) -> User:
    """
    Create a new user.

    Bootstrap rule (see DECISIONS.md D-014):
    - If this is the FIRST user in the system, force role = 'admin'.
    - Otherwise, the requested role applies (the router is responsible for
      having verified the caller is authorized to create users).
    """
    with db.begin():
        # Take a transaction-scoped advisory lock so concurrent bootstraps
        # serialize instead of racing. Released automatically at commit/rollback.
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _BOOTSTRAP_LOCK_KEY},
        )

        is_bootstrap = db.scalar(select(User.id).limit(1)) is None

        if is_bootstrap:
            role = UserRole.ADMIN.value
        else:
            role = (data.role or UserRole.CLERK).value

        user = User(
            email=str(data.email).lower().strip(),
            full_name=data.full_name.strip(),
            hashed_password=hash_password(data.password),
            role=role,
        )
        db.add(user)

        try:
            db.flush()  # surfaces unique violation before commit
        except IntegrityError as exc:
            db.rollback()
            raise EmailAlreadyRegistered() from exc

    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """
    Return the User if credentials are valid and the user is active.
    Return None otherwise.

    Constant-time behavior: whether the email is missing or the password is
    wrong, this function runs an Argon2 verification and returns None.
    This prevents timing-based user enumeration.
    """
    user = db.scalar(select(User).where(User.email == str(email).lower().strip()))

    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None

    if not verify_password(password, user.hashed_password):
        return None

    if not user.is_active:
        return None

    return user