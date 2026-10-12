"""
Auth endpoints: register, login, me.

Keep this file thin. All decisions live in the service.
"""
from app.api.deps import get_current_user
from app.models.user import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import auth as auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user.

    NOTE — for B.2 this endpoint is OPEN. Once B.3 lands the auth dependency,
    we will restrict this endpoint so only an authenticated admin can create
    users (except for the bootstrap case, which the service handles).
    """
    try:
        user = auth_service.create_user(db, payload)
    except auth_service.EmailAlreadyRegistered:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    if user is None:
        # Deliberately vague — never confirm whether an email exists.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token = create_access_token(str(user.id), role=user.role)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    """
    Return the currently authenticated user.

    Any client with a valid, unexpired token for an active user reaches
    this endpoint. The response never contains hashed_password.
    """
    return current_user