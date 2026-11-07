"""
Collection points — where produce is actually handed over (D-039).

Until now a delivery's location was free text on the row, which meant no
report could group by it and no clerk could be tied to one. This entity is the
smallest structured thing that fixes both: a named, coded point with the
geography a cooperative actually uses (county → ward → zone) and an optional
scale id for the weighbridge.

`farmer.collection_point_id` is the member's default point;
`delivery.collection_point_id` is where that delivery happened. The delivery
field is deliberately independent of the farmer's current point: a member who
moves to another point keeps their history at the old one, and a reversal
carries the original's point rather than today's.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class CollectionPoint(BaseModel):
    __tablename__ = "collection_points"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Short human handle printed on reports and quoted by staff: "KSM-CENTRAL".
    code: Mapped[str] = mapped_column(String(24), nullable=False)

    # Structured geography, in the order a co-op says it.
    county: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ward: Mapped[str | None] = mapped_column(String(80), nullable=True)
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Weighbridge / scale identifier, when the point has one. Free text: every
    # scale vendor formats it differently, and inventing a scheme here would
    # be worse than storing what is written on the machine.
    scale_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_collection_point_code"),
        # Codes are typed by staff; keep them to characters that survive a
        # URL, a CSV export and a phone call.
        CheckConstraint(
            r"code ~ '^[A-Z0-9_-]{2,24}$'", name="ck_collection_point_code_format"
        ),
        CheckConstraint(
            "length(trim(name)) > 0", name="ck_collection_point_name_not_empty"
        ),
        # The list screen filters active points by name; this index serves it.
        Index("ix_collection_point_active_name", "is_active", "name"),
    )

    def __repr__(self) -> str:
        return f"<CollectionPoint {self.code} {self.name}>"
