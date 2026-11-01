"""
Audit schemas — response shapes for the admin audit endpoint.

`before`/`after` are deliberately untyped JSON: the fields differ per action
(amount and rate for a payment, status and notes for a farmer). Trying to
model every action's snapshot as a discriminated union would buy type safety
at the read path and cost a schema edit on every new action.

`actor_name` and `entity_label` are resolved server-side so the screen never
issues a lookup per row (D-027). `entity_label` is the human name of the thing
that changed — "Grace Wambui — Coffee" rather than `e0ef997f…`. It is derived,
not stored: the trail records the id, and renaming a farmer must not require
rewriting history.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryResponse(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    # e.g. "Grace Wambui — Coffee". None when the row has since been deleted
    # or the type is not one we can name; the screen falls back to the id.
    entity_label: str | None
    actor_id: uuid.UUID | None
    actor_name: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None
    created_at: datetime


class AuditListResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int
    limit: int
    offset: int
