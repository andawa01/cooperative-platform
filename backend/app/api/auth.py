"""
Auth endpoints: register, login, me.

Keep this file thin. All decisions live in the service.
"""

import uuid as _uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    _unauthorized,
    assert_token_current,
    get_current_user,
    get_token_claims,
)
from app.core.security import create_access_token, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth as auth_service
from app.services import login_throttle, token_denylist

router = APIRouter(prefix="/auth", tags=["auth"])

_bearer_scheme = HTTPBearer(auto_error=False)


def _require_admin_unless_bootstrap(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict | None:
    """
    Allow unauthenticated access only when the users table is empty (bootstrap).
    Once at least one user exists, a valid admin bearer token is required.

    Returns the token's claims (so the caller can attribute the action it
    guards) or None during bootstrap, when no user exists to be the actor.
    """
    is_empty = db.scalar(select(User.id).limit(1)) is None
    if is_empty:
        return None  # bootstrap: no token needed

    if credentials is None or not credentials.credentials:
        raise _unauthorized("Missing bearer token")

    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.PyJWTError:
        raise _unauthorized("Invalid token")

    sub = claims.get("sub")
    try:
        user_id = _uuid.UUID(str(sub))
    except (ValueError, TypeError):
        raise _unauthorized("Invalid token")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Invalid token")

    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")

    # Same revocation rules as every other authenticated endpoint: a token
    # revoked at logout, or invalidated by a password change, cannot create
    # users either (D-030).
    assert_token_current(claims, user)

    return claims


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    claims: dict | None = Depends(_require_admin_unless_bootstrap),
):
    """
    Register a new user.

    - No users exist yet: open (bootstrap). The first user is always admin.
    - Users already exist: valid admin bearer token required.
    """
    # Attribute the account to the admin who created it (None on bootstrap,
    # where there is no actor yet — the audit row says `system`).
    actor_id: _uuid.UUID | None = None
    if claims:
        try:
            actor_id = _uuid.UUID(str(claims.get("sub")))
        except (ValueError, TypeError):
            actor_id = None

    try:
        user = auth_service.create_user(db, payload, actor_id=actor_id)
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Exchange credentials for a token.

    Throttled per account (see services/login_throttle.py for why not per
    IP): the check runs before the password is verified, and the attempt that
    crosses the threshold answers 429 with `Retry-After` rather than 401
    (D-030).
    """
    email = str(payload.email).lower().strip()

    state = login_throttle.check(email)
    if state.limited:
        raise _too_many(state.retry_after)

    user = auth_service.authenticate(db, email, payload.password)
    if user is None:
        # Deliberately vague — never confirm whether an email exists.
        state = login_throttle.record_failure(email)
        if state.limited:
            raise _too_many(state.retry_after)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    login_throttle.reset(email)
    token = create_access_token(
        str(user.id), role=user.role, token_version=user.token_version
    )
    return TokenResponse(access_token=token)


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many failed attempts. Try again later.",
        headers={"Retry-After": str(max(retry_after, 1))},
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    claims: dict = Depends(get_token_claims),
    _: User = Depends(get_current_user),
):
    """
    Revoke the presenting token.

    Puts this token's `jti` on a denylist until its natural expiry, so a
    copied token stops working immediately. Other sessions of the same user
    stay valid (that is what a password change is for).
    """
    jti = claims.get("jti")
    if jti:
        remaining = int(claims.get("exp", 0)) - int(datetime.now(UTC).timestamp())
        token_denylist.revoke(jti, remaining)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Change the caller's password.

    Bumps `token_version`, which invalidates every existing token for this
    user — including the one making this request. The client must sign in
    again with the new password.
    """
    try:
        auth_service.change_password(
            db, user, payload.current_password, payload.new_password
        )
    except auth_service.InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )
    except auth_service.PasswordReused:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="New password must differ from the current one",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """
    Return the currently authenticated user.

    Any client with a valid, unexpired token for an active user reaches
    this endpoint. The response never contains hashed_password.
    """
    return current_user
