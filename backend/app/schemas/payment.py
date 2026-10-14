"""
Payment and allocation schemas.

Money fields are Decimal with the same precision/scale as the DB:
Numeric(12, 4). This is not negotiable.

The PaymentCreate schema accepts optional manual allocations. If omitted,
the service falls back to FIFO allocation against the farmer's oldest
outstanding deliveries.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.payment import PaymentMethod, PaymentStatus


class AllocationInput(BaseModel):
    delivery_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=4)


class PaymentCreate(BaseModel):
    farmer_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=100)
    paid_at: datetime
    idempotency_key: str = Field(min_length=8, max_length=64)
    # If provided, these are the allocations the client wants. If omitted or
    # empty, the service allocates FIFO against the farmer's outstanding
    # deliveries.
    allocations: list[AllocationInput] | None = None
    notes: str | None = None


class PaymentReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AllocationResponse(BaseModel):
    id: uuid.UUID
    delivery_id: uuid.UUID
    amount: Decimal
    reversal_of_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class PaymentResponse(BaseModel):
    id: uuid.UUID
    farmer_id: uuid.UUID
    amount: Decimal
    currency: str
    method: PaymentMethod
    reference: str | None
    paid_at: datetime
    recorded_at: datetime
    recorded_by_id: uuid.UUID
    status: PaymentStatus
    reversal_of_id: uuid.UUID | None
    notes: str | None
    allocations: list[AllocationResponse] = []
    unallocated_amount: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    total: int
    limit: int
    offset: int