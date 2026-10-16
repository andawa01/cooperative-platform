"""
Notification model — the durable record of what we told a farmer.

Postgres holds the canonical fact: "at time T, we sent message M to farmer
F about entity E". Redis holds the dispatch state (queued, attempts,
retries) — see D-024.

Why Postgres for this?
- It must survive a Redis restart. The record of what we told a farmer is
  part of our audit trail.
- It joins naturally to farmers, deliveries, and payments.
- Query patterns include "what did we send this farmer last month?" —
  exactly what a relational DB is for.

Why NOT Postgres for the queue?
- The queue is transient state with retry counters and backoff timestamps.
  It's exactly the shape Redis is optimised for.
- We do not want a queue polluting our money tables with thousands of
  short-lived rows.
"""
import enum
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class NotificationChannel(str, enum.Enum):
    SMS = "sms"


class NotificationTemplate(str, enum.Enum):
    DELIVERY_RECORDED = "delivery_recorded"
    PAYMENT_RECORDED = "payment_recorded"


class RelatedEntityType(str, enum.Enum):
    DELIVERY = "delivery"
    PAYMENT = "payment"


NOTIFICATION_CHANNEL_VALUES = tuple(c.value for c in NotificationChannel)
NOTIFICATION_TEMPLATE_VALUES = tuple(t.value for t in NotificationTemplate)
RELATED_ENTITY_TYPE_VALUES = tuple(e.value for e in RelatedEntityType)


class Notification(BaseModel):
    __tablename__ = "notifications"

    farmer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farmers.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    template: Mapped[str] = mapped_column(String(50), nullable=False)
    recipient: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # The entity this notification is *about* (a delivery, a payment).
    # Nullable in the model so we can send generic announcements later.
    related_entity_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "channel IN (" + ", ".join(f"'{v}'" for v in NOTIFICATION_CHANNEL_VALUES) + ")",
            name="ck_notification_channel_valid",
        ),
        CheckConstraint(
            "template IN (" + ", ".join(f"'{v}'" for v in NOTIFICATION_TEMPLATE_VALUES) + ")",
            name="ck_notification_template_valid",
        ),
        CheckConstraint(
            "related_entity_type IS NULL OR related_entity_type IN ("
            + ", ".join(f"'{v}'" for v in RELATED_ENTITY_TYPE_VALUES) + ")",
            name="ck_notification_related_type_valid",
        ),
        # If one is set, both must be set (they describe the same fact).
        CheckConstraint(
            "(related_entity_type IS NULL) = (related_entity_id IS NULL)",
            name="ck_notification_related_consistency",
        ),
        Index("ix_notification_farmer_created", "farmer_id", "created_at"),
        Index("ix_notification_related", "related_entity_type", "related_entity_id"),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.id} {self.channel} {self.template}>"