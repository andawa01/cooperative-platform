"""
Deduction request/response schemas.

Money is Decimal at the DB's precision (Numeric(12, 4)), as everywhere.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.deduction import DeductionReason


class DeductionCreate(BaseModel):
    farmer_id: uuid.UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    reason_code: DeductionReason
    reference: str | None = Field(default=None, max_length=100)
    applied_at: datetime
    notes: str | None = None


class DeductionReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class DeductionResponse(BaseModel):
    id: uuid.UUID
    farmer_id: uuid.UUID
    # Resolved server-side so a list screen needs no per-row lookup (D-027).
    farmer_name: str
    amount: Decimal
    currency: str
    reason_code: DeductionReason
    reference: str | None
    applied_at: datetime
    recorded_at: datetime
    recorded_by_id: uuid.UUID
    reversal_of_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeductionListResponse(BaseModel):
    items: list[DeductionResponse]
    total: int
    limit: int
    offset: int
