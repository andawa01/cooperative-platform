"""
Farmer statement schemas.

A statement is the chronological story of a farmer's financial position:
what they delivered, what they were paid, and where they stand after each
event. It exposes a running PAIR of figures (debt and credit) rather than
a single balance, matching the ledger model in D-019.

The closing pair MUST equal what /farmers/{id}/balance returns when the
statement covers through today. There is a pytest for exactly that.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

StatementEntryType = Literal[
    "delivery",
    "delivery_reversal",
    "payment",
    "payment_reversal",
]


class StatementOpening(BaseModel):
    outstanding_debt: Decimal
    available_credit: Decimal


class StatementEntry(BaseModel):
    date: datetime
    type: StatementEntryType
    amount: Decimal  # signed: + for credit-to-position, - for the inverse
    description: str
    # At most one of these is set, depending on the type.
    delivery_id: uuid.UUID | None = None
    payment_id: uuid.UUID | None = None
    reversal_of_id: uuid.UUID | None = None
    # Running pair AFTER this event.
    debt_after: Decimal
    credit_after: Decimal


class FarmerStatementResponse(BaseModel):
    farmer_id: uuid.UUID
    # These were once named `from_`/`to` (a Python-keyword workaround) while
    # the service passed `start=`/`end=`. Pydantic rejected the unknown
    # keywords, so every request to this endpoint answered 500 — a bug no test
    # covered until the statement screen tried to use it. Named to match both
    # the service and the client.
    start: datetime
    end: datetime
    currency: str
    opening: StatementOpening
    entries: list[StatementEntry]
    closing: StatementOpening
