"""
Auth schemas — request and response shapes for /auth/* endpoints.

Design notes:
- UserResponse is an ALLOWLIST. It contains only fields the client should see.
  hashed_password is not here, and never will be. If someone adds it by
  accident, the code review will catch it — but the safest defence is that
  it has no business being on this class at all.
- Password minimum length is 10 (deliberate floor; not a strong policy).
  We don't enforce complexity rules (no "must have a digit") because they
  encourage worse passwords, not better. Argon2 makes brute force expensive
  regardless.
- Email is validated by Pydantic's EmailStr.
"""

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole

# One floor for registration and password changes, so "a valid password"
# means the same thing everywhere.
MIN_PASSWORD_LENGTH = 10


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    # Role is optional. If not provided, defaults to 'clerk'.
    # Bootstrap rule (see service): the very first user is forced to 'admin'
    # regardless of what is sent, because there is no one to approve them.
    role: UserRole | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PasswordChangeRequest(BaseModel):
    """Authenticated password change: prove the old one, set the new one."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}
