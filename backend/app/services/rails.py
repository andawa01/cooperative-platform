"""
Payout rails — turning an approved run into something a person can act on.

A rail is the last mile: how the money reaches the member. Today the only
implemented rail is a **file**, because that is what a cooperative treasurer
actually does — upload a bulk payment file to the M-Pesa portal, or hand a
schedule to the bank. The seam is one function, `build_file`, so a real
gateway (M-Pesa B2C API, bank API) can replace a provider later without the
run lifecycle changing: amounts are still frozen at creation, there is still
one approval, and dispatch still records one ordinary `Payment` per member.

What the file is, and is not:

- **Only unpaid members appear.** A row that already has a payment would pay
  that member twice, which is the most expensive mistake a payout file can
  make. Paid and cancelled rows are filtered out rather than trusted to the
  caller.
- **No BOM, no thousands separators.** These files are machine-read by a
  payment portal. The month-end exports (`api/csv.py`) prepend a BOM because
  an accountant opens them in Excel; that reasoning does not apply here.
- **The ledger stays authoritative.** Downloading the file moves no money.
  Dispatching the run records the payments. If a rail later reports a row
  failed, the row is retried — and a payment that was recorded but never
  arrived is corrected by reversing it, never by editing the file.

Bank transfers are registered but refuse with an explanation: a bank EFT file
needs an account number per member, and the member record does not capture one
yet. Refusing is honest; emitting a file with a phone number in the account
column is how a whole payroll bounces.
"""

import csv
import io
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.models.payment import PaymentMethod
from app.models.payout import PayoutBatch, PayoutItemStatus, PayoutStatus

# Whole minor units. A payment portal rejects `500.0000`; the ledger keeps its
# four decimals, the file carries the amount the rail can actually pay.
_MINOR = Decimal("0.01")

_UNPAID = (PayoutItemStatus.PENDING.value, PayoutItemStatus.FAILED.value)


class RailError(Exception):
    """The run cannot be turned into a file right now, for a stated reason."""


class NoRailForMethod(RailError):
    """This method has no file — cash is paid across a counter."""


class NothingToPay(RailError):
    """Every member in the run is already paid; a file would pay them twice."""


class MissingDestination(RailError):
    """A row has no phone number, so a mobile-money file cannot address it."""

    def __init__(self, members: Sequence[str]):
        self.members = list(members)
        names = ", ".join(self.members[:5])
        if len(self.members) > 5:
            names += f" and {len(self.members) - 5} more"
        super().__init__(
            f"No phone number on file for {names}. Add one before generating "
            "the file, or the member will be skipped without anyone noticing."
        )


@dataclass(frozen=True)
class RailRow:
    """
    One member's line, already resolved for the rail.

    Deliberately not the ORM item: a rail needs a destination and a name, which
    live on the farmer, and a file builder should not be able to reach back
    into the session and issue a query per row (D-027).
    """

    farmer_id: uuid.UUID
    farmer_name: str
    phone: str | None
    amount: Decimal
    currency: str
    status: str


@dataclass(frozen=True)
class RailFile:
    rail: str
    filename: str
    content: str
    row_count: int


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def _csv(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(list(header))
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue()


def _amount(value: Decimal) -> str:
    return f"{value.quantize(_MINOR, rounding=ROUND_HALF_UP):f}"


def _unique_name(reference: str | None, batch: PayoutBatch) -> str:
    """Safe for a portal's free-text column: alphanumeric, short, stable."""
    base = reference or f"RUN{batch.id.hex[:8].upper()}"
    cleaned = re.sub(r"[^A-Za-z0-9]", "", base)
    return cleaned[:20]


def _msisdn(phone: str) -> str:
    """The M-Pesa portal wants `254712345678`, not `+254712345678`."""
    return re.sub(r"[^0-9]", "", phone)


def _filename(prefix: str, batch: PayoutBatch, today: date) -> str:
    handle = batch.reference or batch.id.hex[:8].upper()
    safe = re.sub(r"[^A-Za-z0-9-]", "", handle)
    return f"{prefix}-{safe}-{today.isoformat()}.csv"


# ---------------------------------------------------------------------------
# Rails
# ---------------------------------------------------------------------------

# The bulk-upload columns of the M-Pesa B2C portal: one row pays one number.
MPESA_HEADER = (
    "CommandID",
    "UniqueName",
    "Amount",
    "MSISDN",
    "Remarks",
    "Occasion",
)


def _mpesa(batch: PayoutBatch, rows: Sequence[RailRow], today: date) -> RailFile:
    if batch.currency != "KES":
        raise RailError(
            f"M-Pesa pays in KES, and this run is in {batch.currency}. "
            "Use a bank or cash run for another currency."
        )

    missing = [row.farmer_name for row in rows if not row.phone]
    if missing:
        raise MissingDestination(missing)

    reference = batch.reference or f"RUN{batch.id.hex[:8].upper()}"
    unique_name = _unique_name(batch.reference, batch)
    body = [
        (
            "BusinessPayment",
            unique_name,
            _amount(row.amount),
            _msisdn(row.phone or ""),
            f"Payout {reference}"[:100],
            reference[:100],
        )
        for row in rows
    ]

    return RailFile(
        rail="mpesa_b2c",
        filename=_filename("mpesa-b2c", batch, today),
        content=_csv(MPESA_HEADER, body),
        row_count=len(body),
    )


def _bank(batch: PayoutBatch, rows: Sequence[RailRow], today: date) -> RailFile:
    """
    Refuse rather than emit a file that cannot be paid.

    A bank EFT schedule identifies the beneficiary by bank and account number.
    The member record carries a phone and a national id, neither of which a
    bank can credit. Until account details exist on the member (and are
    validated — a wrong digit here is money sent to a stranger), a bank run is
    paid by recording the payments individually.
    """
    raise RailError(
        "A bank file needs each member's bank and account number, which the "
        "member record does not capture yet. Pay this run by mobile money, or "
        "record the transfers individually."
    )


def _cash(batch: PayoutBatch, rows: Sequence[RailRow], today: date) -> RailFile:
    raise NoRailForMethod(
        "Cash runs are paid across the counter — there is no file to upload. "
        "Dispatch the run to record the payments against this list."
    )


_RAILS = {
    PaymentMethod.MOBILE_MONEY.value: _mpesa,
    PaymentMethod.BANK_TRANSFER.value: _bank,
    PaymentMethod.CASH.value: _cash,
}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_file(
    batch: PayoutBatch,
    rows: Sequence[RailRow],
    *,
    today: date | None = None,
) -> RailFile:
    """
    The disbursement file for a run, or a `RailError` explaining why not.

    Unpaid rows only. A cancelled run produces nothing: its members were never
    promised anything by this run.
    """
    if batch.status == PayoutStatus.CANCELLED.value:
        raise RailError("This run was cancelled, so there is nothing to pay.")

    rail = _RAILS.get(batch.method)
    if rail is None:  # unreachable while the CHECK constraint holds
        raise NoRailForMethod(f"'{batch.method}' has no payout rail.")

    unpaid = [row for row in rows if row.status in _UNPAID]
    if not unpaid:
        raise NothingToPay(
            "Every member in this run already has a payment recorded. "
            "A second file would pay them twice."
        )

    return rail(batch, unpaid, today or date.today())
