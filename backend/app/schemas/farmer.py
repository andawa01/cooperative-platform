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
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models.farmer import FarmerStatus

# E.164: + then 1-9 then 6-14 digits. Same regex as the DB CHECK.
E164_PATTERN = r"^\+[1-9][0-9]{6,14}$"

# Digits only, same as the DB CHECK. Leading zeros are meaningful, so the
# account is a string everywhere — never an int.
BANK_ACCOUNT_PATTERN = r"^[0-9]{6,20}$"


class FarmerCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    # Loose shape check only. The service normalizes to E.164 and rejects
    # anything it cannot normalize. See DECISIONS.md D-016.
    phone: str = Field(min_length=7, max_length=20)
    date_of_birth: date | None = None
    national_id: str | None = Field(default=None, max_length=50)
    # Bank details are optional, but only as a pair. Validated here for a
    # create, where both fields are present in the same payload; for a PATCH
    # the service compares against what is already stored.
    bank_name: str | None = Field(default=None, max_length=100)
    bank_account_number: str | None = Field(default=None, pattern=BANK_ACCOUNT_PATTERN)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @model_validator(mode="after")
    def _bank_details_together(self) -> "FarmerCreate":
        if (self.bank_name is None) != (self.bank_account_number is None):
            raise ValueError(
                "bank_name and bank_account_number must be provided together"
            )
        return self


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
    bank_name: str | None = Field(default=None, max_length=100)
    bank_account_number: str | None = Field(default=None, pattern=BANK_ACCOUNT_PATTERN)
    location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class FarmerResponse(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    phone: str
    date_of_birth: date | None
    national_id: str | None
    bank_name: str | None
    bank_account_number: str | None
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


class BankDetailsImportRequest(BaseModel):
    """
    The CSV file's text, not an upload: the browser reads the file and sends
    what it found, so there is one parser (the server's) and no multipart
    dependency. `dry_run` defaults to true — importing money destinations is
    something an admin confirms after seeing who it matched.
    """

    csv: str = Field(min_length=1, max_length=1_000_000)
    dry_run: bool = True


class BankDetailsImportRow(BaseModel):
    line: int
    phone: str
    farmer_name: str | None
    status: Literal["valid", "applied", "error"]
    message: str | None

    model_config = {"from_attributes": True}


class BankDetailsImportResult(BaseModel):
    dry_run: bool
    total: int
    valid: int
    applied: int
    errors: int
    rows: list[BankDetailsImportRow]

    model_config = {"from_attributes": True}
