"""
Auth service — registration and login logic.

Layering: this module does not import FastAPI. It returns domain objects or
raises domain errors. The router translates those into HTTP responses.
"""

import logging
import uuid as _uuid

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.db.session import write_transaction
from app.models.user import User, UserRole
from app.schemas.auth import RegisterRequest
from app.services import audit

log = logging.getLogger(__name__)


class EmailAlreadyRegistered(Exception):
    """Raised when attempting to register an email that already exists."""


class InvalidCredentials(Exception):
    """Current password did not verify during a password change."""


class PasswordReused(Exception):
    """The new password is the one already in use."""


# A pre-computed Argon2 hash used ONLY as a timing decoy.
# When login is attempted for a non-existent email, we verify against this
# dummy so the response time is the same as for a wrong password. Without
# this, an attacker can time the login endpoint to determine which emails
# are registered. See authenticate() below.
_DUMMY_HASH = hash_password("this-is-never-a-real-password")


# Advisory lock key used for the bootstrap operation. Arbitrary but constant —
# every process that wants to bootstrap takes this same lock.
_BOOTSTRAP_LOCK_KEY = 8675309


def create_user(
    db: Session,
    data: RegisterRequest,
    actor_id: _uuid.UUID | None = None,
) -> User:
    """
    Create a new user.

    Bootstrap rule (see DECISIONS.md D-014):
    - If this is the FIRST user in the system, force role = 'admin'.
    - Otherwise, the requested role applies (the router is responsible for
      having verified the caller is authorized to create users).

    `actor_id` is the authenticated admin who approved this account, or None
    during bootstrap — when there is no user yet to be the actor, and the
    system is doing the registering.
    """
    with write_transaction(db):
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

        # Same transaction as the insert. Never records the password hash.
        audit.record(
            db,
            actor_id=actor_id,
            action="user.create",
            entity_type="user",
            entity_id=user.id,
            after={
                "email": user.email,
                "full_name": user.full_name,
                "role": role,
                "bootstrap": is_bootstrap,
            },
        )

    db.refresh(user)
    return user


def change_password(
    db: Session, user: User, current_password: str, new_password: str
) -> User:
    """
    Change a password and invalidate every session for that user.

    The `token_version` bump is the point: a password change is usually a
    response to suspicion, so leaving the old tokens alive for their
    remaining hours would defeat the purpose (D-030).
    """
    if not verify_password(current_password, user.hashed_password):
        raise InvalidCredentials()

    if verify_password(new_password, user.hashed_password):
        raise PasswordReused()

    with write_transaction(db):
        previous_version = user.token_version or 0
        user.hashed_password = hash_password(new_password)
        user.token_version = previous_version + 1

        # A password change is the classic "who did this, and when?" event.
        # Versions only: hashes and passwords never enter the trail.
        audit.record(
            db,
            actor_id=user.id,
            action="user.password_change",
            entity_type="user",
            entity_id=user.id,
            before={"token_version": previous_version},
            after={
                "token_version": user.token_version,
                "sessions_invalidated": True,
            },
        )

    log.info("password changed for user %s", user.id)
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
