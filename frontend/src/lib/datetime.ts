/**
 * Date display, in one place.
 *
 * Everything renders as day/month/year on a 24-hour clock, formatted by hand
 * rather than through `toLocale*String()`:
 *
 * - **The browser locale is not the co-op's locale.** A laptop set to en-US
 *   renders 5 March as `3/5/2026`, which a clerk in Nairobi reads as the 3rd
 *   of May. On a delivery record that ambiguity is the start of a dispute.
 * - **Locale output is not stable across machines.** `toLocale*String()`
 *   depends on the browser's ICU build, so two clerks in the same office could
 *   see the same row formatted differently.
 * - **Sorting and scanning.** `dd/mm/yyyy` keeps a dense table column the same
 *   width and orders correctly as text within a year.
 *
 * Times are shown in local time, which is what the operator is thinking in —
 * the API sends UTC and `recorded_at` carries the authoritative instant.
 */

const pad = (value: number): string => String(value).padStart(2, '0')

/**
 * Parse a value into a Date, or null when it is absent/invalid.
 *
 * A date-only string (`2025-06-15`, as used by `date_of_birth` and rate
 * `effective_from`) is a *calendar date*, not an instant. `new Date()` would
 * read it as UTC midnight, which shifts to the previous day west of UTC — so
 * those are built from their components instead.
 */
function toDate(value: string | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value
  }

  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (dateOnly) {
    const [, year, month, day] = dateOnly
    return new Date(Number(year), Number(month) - 1, Number(day))
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

/** `15/06/2025`. Returns an em dash for a missing or unparseable value. */
export function formatDate(value: string | Date | null | undefined): string {
  const date = toDate(value)
  if (!date) return '—'
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()}`
}

/** `14:32`. Returns an em dash for a missing or unparseable value. */
export function formatTime(value: string | Date | null | undefined): string {
  const date = toDate(value)
  if (!date) return '—'
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** `15/06/2025, 14:32`. */
export function formatDateTime(value: string | Date | null | undefined): string {
  const date = toDate(value)
  if (!date) return '—'
  return `${formatDate(date)}, ${formatTime(date)}`
}

/**
 * `15/06` — for dense contexts such as chart axes, where the year is implied
 * by the surrounding period.
 */
export function formatDayMonth(value: string | Date | null | undefined): string {
  const date = toDate(value)
  if (!date) return '—'
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}`
}

/**
 * Today as `YYYY-MM-DD`, for `<input type="date">` values and API query
 * parameters. Deliberately NOT localised: the browser and the API both expect
 * ISO here, and the control renders it in the user's locale itself.
 */
export function toIsoDate(date: Date = new Date()): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}
