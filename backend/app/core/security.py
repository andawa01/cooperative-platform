"""
Security primitives: password hashing and JWT encode/decode.

This module is deliberately small and dependency-free — it does not import
models, services, or routers. It is a pure utility layer.

Design notes:
- Passwords are hashed with Argon2id (OWASP-recommended, memory-hard).
  We never store plaintext and never use SHA/MD5 for passwords.
- JWTs are HS256, signed with settings.jwt_secret_key. The token asserts
  IDENTITY (who you are). It does NOT assert permission — permissions
  are always re-checked against the DB (see B.3).
- The token payload contains: sub (user id), exp (expiry), iat (issued at),
  and role. Role is informational for the frontend; it is never trusted
  for authorization because it can be stale.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# Argon2id is the current OWASP recommendation. `deprecated="auto"` lets
# passlib transparently upgrade hashes when we change parameters later.
_pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=2,
    argon2__memory_cost=65536,  # 64 MB
    argon2__parallelism=2,
)


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Returns an opaque string safe to store."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time-ish verification of a plaintext password against a hash."""
    return _pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str,
    role: str | None = None,
    expires_delta: timedelta | None = None,
    token_version: int = 0,
) -> str:
    """
    Create a signed JWT.

    subject: the user id (as a string).
    role: optional, included for the frontend's convenience only.
    expires_delta: override the default lifetime (e.g. for tests).
    token_version: the user's `token_version` at issue time. Authorization
        rejects the token if the row has moved on (D-030).

    `jti` is unique per token so a single token can be revoked on logout
    without invalidating the user's other sessions.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
        "ver": token_version,
    }
    if role is not None:
        payload["role"] = role

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises jwt.PyJWTError (or a subclass like ExpiredSignatureError) on any
    problem: bad signature, expired, malformed. Callers should catch and
    translate to a 401.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
