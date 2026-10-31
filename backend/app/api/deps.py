"""
Shared FastAPI dependencies.

Two dependencies and one factory:

- get_current_user: extracts + validates the bearer token, loads the user
  from the DB, and rejects if the user is inactive.
- require_role(*roles): a factory that returns a dependency enforcing that
  the current user's role is in the given set.

Auth decisions follow D-012 and D-014:
- The token asserts IDENTITY (who you are).
- The DB asserts PERMISSION (what you can do, right now).
- An inactive user is rejected even if their token is valid and unexpired.
- Missing/invalid auth → 401. Insufficient permission → 403.
"""

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services import token_denylist

# auto_error=False so we can raise our own 401 instead of FastAPI's default
# 403 when the Authorization header is missing. See D-014.
_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    """
    Build a 401 with the standard WWW-Authenticate header.

    The header is required by RFC 7235. Without it some clients and
    proxies treat the response as ambiguous.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_token_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """
    Decode and verify the bearer token, or raise 401.

    This answers "is the token authentic?" only. It deliberately does not
    touch the database. `get_current_user` builds on it and adds the
    database-backed checks (existence, active, revocation).

    FastAPI caches dependency results per request, so an endpoint that
    depends on both this and `get_current_user` decodes the token once.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.PyJWTError:
        # Deliberately vague — do not leak whether the signature failed or
        # the token was malformed. See D-014.
        raise _unauthorized("Invalid token")


def assert_token_current(claims: dict, user: User) -> None:
    """
    Reject a token that is no longer valid for an otherwise-good user.

    Two ways a token outlives its welcome:
      - it was revoked at logout (`jti` on the Redis denylist), or
      - the user's password changed after it was minted (`ver` claim).

    Kept in one place on purpose. `get_current_user` is the normal path, but
    `/auth/register` needs its own guard so the bootstrap case can accept a
    missing token — and that guard must not silently drift back to trusting
    a token these checks would reject. Missing `ver` (tokens minted before
    the column existed) reads as 0.
    """
    if token_denylist.is_revoked(claims.get("jti")):
        raise _unauthorized("Token revoked")

    if int(claims.get("ver", 0)) != (user.token_version or 0):
        raise _unauthorized("Token revoked")


def get_current_user(
    claims: dict = Depends(get_token_claims),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the current authenticated user from the request.

    Steps:
      1. Decode + verify the token (get_token_claims).
      2. Reject if the token was revoked at logout (jti denylist).
      3. Load the user from the DB by id. Missing user → 401.
      4. Reject an inactive account → 401.
      5. Reject a token minted before the last password change
         (`ver` claim vs users.token_version).

    The returned object is a live User ORM instance: role and status are the
    authoritative state, never the token's claims (D-015).
    """
    sub = claims.get("sub")
    if not sub:
        raise _unauthorized("Invalid token")

    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError):
        raise _unauthorized("Invalid token")

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("Invalid token")

    if not user.is_active:
        # We deliberately use 401 (not 403) here. A deactivated account is
        # treated like an unauthenticated one — the caller has no standing.
        raise _unauthorized("Account is inactive")

    # Denylist (logout) and token_version (password change).
    assert_token_current(claims, user)

    return user


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory.

    Usage:
        @router.post("/rates", dependencies=[Depends(require_role(UserRole.ADMIN))])
        def create_rate(...): ...

    Or, if the endpoint needs the user object:
        def create_rate(user: User = Depends(require_role(UserRole.ADMIN))): ...

    Returns 403 (not 401) when the user is authenticated but lacks the role.
    The distinction matters: 401 = "we don't know who you are",
    403 = "we know who you are, and you're not allowed".
    """
    if not allowed_roles:
        raise ValueError("require_role requires at least one role")

    allowed_values = {r.value for r in allowed_roles}

    def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _checker
