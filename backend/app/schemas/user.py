"""
User administration schemas.

`UserUpdateRequest` is a partial update: every field is optional and only the
ones provided are considered. A field that is present but equal to the
current value is not a change, and produces no audit entry — the same rule
`farmer.update` follows.
"""

from pydantic import BaseModel, Field

from app.models.user import UserRole
from app.schemas.auth import UserResponse


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    limit: int
    offset: int
