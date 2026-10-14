"""
Produce line and rate schemas.

Design notes:
- ProduceLine.code is immutable after creation. It's used in filters, reports,
  and external integrations; changing it would break references.
- ProduceLine.unit is immutable after creation (see D-018). Changing kg to
  liter would silently reinterpret every historical delivery.
- Rates are append-only. There is no update or delete schema. The only way
  to change the future rate is to close the current one and insert a new one.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProduceLineCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50, pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=20)
    description: str | None = None


class ProduceLineUpdate(BaseModel):
    """PATCH semantics. name and description are editable; code and unit are not."""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class ProduceLineResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    unit: str
    description: str | None
    is_active: bool
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProduceLineListResponse(BaseModel):
    items: list[ProduceLineResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------

class RateCreate(BaseModel):
    rate_per_unit: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    effective_from: date


class RateResponse(BaseModel):
    id: uuid.UUID
    produce_line_id: uuid.UUID
    rate_per_unit: Decimal
    currency: str
    effective_from: date
    effective_to: date | None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RateCreateResponse(BaseModel):
    """
    Response for POST /produce-lines/{id}/rates.

    Returns both the new rate and the previously-open rate (now closed), if
    one existed. This lets the client update the full timeline in one call
    without a follow-up request.
    """
    new_rate: RateResponse
    previous_rate: RateResponse | None
    # Number of existing deliveries recorded in the affected window whose
    # rate_snapshot may no longer match the newly-set rate. These deliveries
    # are NOT automatically corrected (see D-018); this count is a warning.
    affected_deliveries: int


class CurrentRateResponse(BaseModel):
    """
    200 { "rate": null } means the produce line exists but has no rate in
    effect for the requested date. A missing produce line is still a 404.
    """
    rate: RateResponse | None