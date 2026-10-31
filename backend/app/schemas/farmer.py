"""
Farmer schemas — request and response contracts.

Design notes:
- Phone is validated as E.164 at the schema layer, and normalized at the
  service layer. The schema rejects obviously-wrong formats early; the
  service handles the business rules (normalization is a business rule,
  not a shape rule).
- The update schema uses PATCH semantics: every field is optional; only
  provided fields are updated. Missing ≠ None.
- FarmerResponse is an ALLOWLIST. Never add a field just because the
  model has it.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.farmer import FarmerStatus

# E.164: + then 1-9 then 6-14 digits. Same regex as the DB CHECK.
E164_PATTERN = r"^\+[1-9][0-9]{6,14}$"


class FarmerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    # Loose shape check only. The service normalizes to E.164 and rejects
    # anything it cannot normalize. See DECISIONS.md D-016.
    phone: str = Field(min_length=7, max_length=20)
    date_of_birth: date | None = None
    national_id: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class FarmerUpdate(BaseModel):
    """
    PATCH semantics. Every field optional; `None` explicitly clears a field
    only if the client sends JSON `null`. Omitted = no change.

    NOT patchable here (deliberately):
      phone        — has its own endpoint (changes SMS destination)
      status       — has dedicated transition endpoints
      merged_into  — set only via the merge endpoint
      created_by   — audit field, immutable
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    national_id: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class FarmerResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    phone: str
    date_of_birth: date | None
    national_id: str | None
    location: str | None
    notes: str | None
    status: FarmerStatus
    verified_at: datetime | None
    merged_into_id: uuid.UUID | None
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FarmerListResponse(BaseModel):
    items: list[FarmerResponse]
    total: int
    limit: int
    offset: int
