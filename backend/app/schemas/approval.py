"""Approval request schemas (D-038)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.approval import ApprovalStatus

ApprovalAction = Literal["payment.reverse", "deduction.reverse", "payout.dispatch"]


class ApprovalCreate(BaseModel):
    """
    Ask for a second admin.

    The server derives the amount, currency and summary from the subject, so
    an approval cannot describe one figure and release another.
    """

    action: ApprovalAction
    entity_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)


class ApprovalDecision(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class ApprovalResponse(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    amount: Decimal | None
    currency: str | None
    summary: str
    reason: str | None
    status: ApprovalStatus
    requested_by_id: uuid.UUID
    requested_by_name: str
    decided_by_id: uuid.UUID | None
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApprovalListResponse(BaseModel):
    items: list[ApprovalResponse]
    total: int
    limit: int
    offset: int
