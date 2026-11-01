"""
CSV export helpers.

Every list screen has an export endpoint, and they all produce the same
thing: RFC 4180 CSV, UTF-8, CRLF line endings, and a filename the accountant
can sort chronologically.

Three decisions worth knowing:

- **A BOM is prepended.** Excel on Windows is the default consumer. Without
  it, a non-ASCII name arrives as mojibake, and the first support ticket of
  every deployment is "the file is broken".
- **Money keeps full precision and no formatting.** No thousands separators,
  no currency symbol — `1234.5000`, not `KES 1,234.50`. A spreadsheet must be
  able to SUM the column without cleaning it first.
- **Text cells are guarded against formula injection.** A farmer note
  beginning with `=` executes when the file is opened. We prefix a tab so the
  value stays readable and inert. Numbers are never touched, so negative
  money still sums correctly.
"""

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Response

# Hard cap on rows per export. An unbounded export holds a database
# transaction open for as long as the browser takes to download, which on a
# rural connection can be minutes. 10k rows is a season of deliveries for a
# mid-sized co-op and roughly 2 MB of CSV.
MAX_EXPORT_ROWS = 10_000

BOM = "\ufeff"


def _inert(text: str) -> str:
    """
    Neutralise a cell a spreadsheet would treat as a formula.

    Only `=` and `@` are unconditionally dangerous. A leading `+` or `-` is
    dangerous *unless the remainder is a number* — which is exactly the case
    for an E.164 phone (`+254712345678`) and for negative money. Guarding
    those would put a tab inside every phone number in the file, and the phone
    is the SMS destination; that is a worse bug than the one being prevented.
    """
    if not text:
        return text

    first = text[0]
    if first in "=\t\r@":
        return "\t" + text
    if first in "+-":
        try:
            float(text)
        except ValueError:
            return "\t" + text
    return text


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return _inert(str(value))


def csv_response(
    *,
    filename: str,
    header: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> Response:
    """
    Build a downloadable CSV response.

    Rows are already materialised by the caller, so this stays a pure
    serialisation step with no session or ORM awareness.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(list(header))
    for row in rows:
        writer.writerow([_cell(value) for value in row])

    return Response(
        content=(BOM + buffer.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Exports are user-specific and never cacheable.
            "Cache-Control": "no-store",
        },
    )
