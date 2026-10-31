"""
Shared base model.

Every table in ShambaTrack inherits from BaseModel, which gives it:
- id: UUID primary key (safer than integer IDs — not guessable, good for multi-tenant)
- created_at: timestamp, set on insert
- updated_at: timestamp, updated on every change

Why UUID over integer?
- Integer IDs leak information ("we have 47 farmers") and are guessable in URLs
- UUIDs work if we ever split the DB or add multi-tenancy
- Downside: slightly larger storage, slightly less human-readable in logs
- For a system where money and identity are involved, this tradeoff is worth it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BaseModel(Base):
    """
    Abstract base — not a table itself. Concrete models inherit from this.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
