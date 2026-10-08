"""
User model — represents an authenticated actor in the system.

For now this covers admins and clerks. Farmers will get their own model
because they have a different relationship with the system (they don't log in
the same way — they receive SMS, they're paid, they're registered by clerks).

We'll layer role modelling on top of this later.
"""
from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class User(BaseModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # role: we'll add this properly later; temporary string field
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="clerk")