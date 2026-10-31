"""
Notification schemas.

The API response merges two sources:
- The durable record from Postgres (this schema's base fields)
- The current dispatch state from Redis (status, attempts, last_error, sent_at)

That merge is what makes the two-store design visible: the *fact* of a
notification lives in Postgres, its *progress* through the pipeline lives
in Redis.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.notification import (
    NotificationChannel,
    NotificationTemplate,
    RelatedEntityType,
)

# Dispatch state — mirrors what we store in Redis.
# "unknown" covers two edge cases: Redis unreachable at read time, or a
# notification that exists in Postgres but whose Redis hash has been evicted.
DispatchStatus = Literal["queued", "sending", "sent", "failed", "unknown"]


class NotificationResponse(BaseModel):
    # Postgres fields
    id: uuid.UUID
    farmer_id: uuid.UUID
    channel: NotificationChannel
    template: NotificationTemplate
    recipient: str
    content: str
    related_entity_type: RelatedEntityType | None
    related_entity_id: uuid.UUID | None
    created_at: datetime

    # Redis fields
    status: DispatchStatus
    attempts: int
    last_error: str | None
    sent_at: datetime | None

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int
