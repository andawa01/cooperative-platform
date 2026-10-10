"""
User model — represents an authenticated actor in the system.

Two roles for MVP (see DECISIONS.md D-012):
- admin: manages rates, verifies farmers, authorizes reversals
- clerk: records farmers, deliveries, and payments

Farmers are NOT users of this system in MVP. See D-003 (Farmer != User).
"""
import enum

from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CLERK = "clerk"


USER_ROLE_VALUES = tuple(r.value for r in UserRole)


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.CLERK.value,
        server_default=UserRole.CLERK.value,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN (" + ", ".join(f"'{v}'" for v in USER_ROLE_VALUES) + ")",
            name="ck_user_role_valid",
        ),
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"