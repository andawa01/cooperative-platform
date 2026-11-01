"""
Dashboard response schemas.

One call returns every number a cooperative manager needs to answer:
- How much do we owe?               (outstanding_debt_total)
- Which produce line is growing?    (deliveries_by_line)
- Who recorded what?                (recent_activity includes recorder)
- How active have we been?          (deliveries_daily, *_in_period)
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class FarmersByStatus(BaseModel):
    pending_verification: int = 0
    active: int = 0
    suspended: int = 0
    archived: int = 0
    merged: int = 0


class DeliveriesByLine(BaseModel):
    produce_line_id: uuid.UUID
    produce_line_name: str
    unit: str
    count: int
    quantity: Decimal
    value: Decimal


class DeliveriesDaily(BaseModel):
    date: date
    count: int
    value: Decimal


class ActivityItem(BaseModel):
    type: Literal[
        "delivery",
        "delivery_reversal",
        "payment",
        "payment_reversal",
        "deduction",
        "deduction_reversal",
    ]
    id: uuid.UUID
    at: datetime
    description: str
    amount: Decimal | None
    currency: str | None
    farmer_id: uuid.UUID
    farmer_name: str


class DashboardSummary(BaseModel):
    generated_at: datetime
    period_days: int
    currency: str

    # Farmer counts
    farmers_total: int
    farmers_by_status: FarmersByStatus

    # Period activity
    deliveries_in_period: int
    deliveries_value_in_period: Decimal
    payments_in_period: int
    payments_value_in_period: Decimal
    deductions_in_period: int
    deductions_value_in_period: Decimal

    # Global financial position
    outstanding_debt_total: Decimal
    available_credit_total: Decimal
    # What has been withheld from members, net of reversals (all time).
    deductions_total: Decimal
    # debt - credit - deductions: what the co-op actually owes across all
    # members. Negative is arrears, i.e. members owing the co-op.
    net_payable_total: Decimal
    pending_valuation_count: int

    # Charts
    deliveries_by_line: list[DeliveriesByLine]
    deliveries_daily: list[DeliveriesDaily]

    # Recent activity feed
    recent_activity: list[ActivityItem]
