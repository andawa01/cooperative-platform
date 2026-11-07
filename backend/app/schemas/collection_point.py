"""Collection point schemas and the production-by-point report (D-039)."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

# Codes are upper-cased by the service, so this accepts lower-case input but
# stores one canonical form.
POINT_CODE_PATTERN = r"^[A-Za-z0-9_-]{2,24}$"


class CollectionPointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(pattern=POINT_CODE_PATTERN)
    county: str | None = Field(default=None, max_length=80)
    ward: str | None = Field(default=None, max_length=80)
    zone: str | None = Field(default=None, max_length=80)
    scale_id: str | None = Field(default=None, max_length=64)

    @field_validator("code", mode="before")
    @classmethod
    def _strip_code(cls, value):
        # Staff paste codes from a spreadsheet; surrounding space is not a
        # validation error, it is a copy-paste artefact.
        return value.strip() if isinstance(value, str) else value


class CollectionPointUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, pattern=POINT_CODE_PATTERN)
    county: str | None = Field(default=None, max_length=80)
    ward: str | None = Field(default=None, max_length=80)
    zone: str | None = Field(default=None, max_length=80)
    scale_id: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None

    @field_validator("code", mode="before")
    @classmethod
    def _strip_code(cls, value):
        return value.strip() if isinstance(value, str) else value


class CollectionPointResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    county: str | None
    ward: str | None
    zone: str | None
    scale_id: str | None
    is_active: bool
    created_by_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionPointListResponse(BaseModel):
    items: list[CollectionPointResponse]
    total: int
    limit: int
    offset: int


class ProductionByPointRow(BaseModel):
    """Net intake for one point in the period."""

    collection_point_id: uuid.UUID | None
    collection_point_name: str
    collection_point_code: str | None
    entries: int
    quantity: Decimal
    value: Decimal
    currency: str


class ProductionByPointResponse(BaseModel):
    delivered_from: str | None
    delivered_to: str | None
    items: list[ProductionByPointRow]
