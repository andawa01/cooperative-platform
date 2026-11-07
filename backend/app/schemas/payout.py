"""
Payout run request/response schemas.

Money is Decimal to the DB's scale (Numeric(12, 4)), as everywhere.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.payment import PaymentMethod
from app.models.payout import PayoutItemStatus, PayoutStatus


class PayoutCreate(BaseModel):
    """
    Start a run.

    With no `farmer_ids`, every active member with a positive payable is
    included. With them, exactly those members — an admin excluding someone
    whose balance is disputed should not have to edit rows afterwards.
    """

    farmer_ids: list[uuid.UUID] | None = None
    method: PaymentMethod = PaymentMethod.MOBILE_MONEY
    notes: str | None = Field(default=None, max_length=500)


class PayoutItemResponse(BaseModel):
    id: uuid.UUID
    farmer_id: uuid.UUID
    farmer_name: str
    # Carried because a rail file needs the destination, not a name: the phone
    # pays by M-Pesa, the bank pair pays by transfer (D-036).
    phone: str | None
    bank_name: str | None
    bank_account_number: str | None
    amount: Decimal
    currency: str
    status: PayoutItemStatus
    payment_id: uuid.UUID | None
    error: str | None
    dispatched_at: datetime | None


class PayoutBatchResponse(BaseModel):
    id: uuid.UUID
    reference: str | None
    currency: str
    method: PaymentMethod
    status: PayoutStatus
    notes: str | None
    created_by_id: uuid.UUID
    approved_by_id: uuid.UUID | None
    approved_at: datetime | None
    dispatched_at: datetime | None
    created_at: datetime
    updated_at: datetime

    # Derived from the items, never stored (D-010).
    total_amount: Decimal
    item_count: int
    paid_count: int
    failed_count: int


class PayoutBatchDetail(PayoutBatchResponse):
    items: list[PayoutItemResponse]


class PayoutListResponse(BaseModel):
    items: list[PayoutBatchResponse]
    total: int
    limit: int
    offset: int


class PayoutDispatchResult(BaseModel):
    """Outcome of one dispatch pass, so the screen can report it honestly."""

    batch: PayoutBatchResponse
    paid: int
    failed: int
    pending: int
