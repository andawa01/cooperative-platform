"""
Delivery schemas.

- DeliveryCreate: what a clerk submits to record a delivery.
- DeliveryValueRequest: what an admin submits to value a pending delivery.
- DeliveryReverseRequest: what an admin submits to reverse a delivery.
- DeliveryResponse: allowlist of what clients see.
- BalanceResponse: the three-figure financial position.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class DeliveryCreate(BaseModel):
    farmer_id: uuid.UUID
    produce_line_id: uuid.UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    delivered_at: datetime
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class DeliveryValueRequest(BaseModel):
    """
    Value a delivery that was recorded without an applicable rate.

    The service looks up the rate effective on the delivery's delivered_at
    at the moment of valuation and snapshots it. If no rate exists even now,
    the operation fails.
    """

    pass  # no body needed; the service derives everything


class DeliveryReverseRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class DeliveryResponse(BaseModel):
    id: uuid.UUID
    farmer_id: uuid.UUID
    produce_line_id: uuid.UUID
    # Display names resolved at read time by the router. A delivery row only
    # stores ids; every list screen needs to show whose delivery it is, and
    # making the client join that would be an N+1 across the whole page.
    farmer_name: str
    produce_line_name: str
    quantity: Decimal
    delivered_at: datetime
    recorded_at: datetime
    recorded_by_id: uuid.UUID
    rate_snapshot: Decimal | None
    currency_snapshot: str
    amount: Decimal | None  # computed; None if unvalued
    reversal_of_id: uuid.UUID | None
    location: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeliveryListResponse(BaseModel):
    items: list[DeliveryResponse]
    total: int
    limit: int
    offset: int


class BalanceResponse(BaseModel):
    farmer_id: uuid.UUID
    currency: str
    outstanding_debt: Decimal
    allocated_to_deliveries: Decimal
    available_credit: Decimal
    pending_valuation_deliveries: int
