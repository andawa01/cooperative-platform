/**
 * Shared data table.
 *
 * One implementation for every list screen, modelled on the ICRMS data table:
 * a bordered card, a muted header row with small uppercase labels, ruled rows
 * with hover, an optional toolbar strip, an in-table empty state, skeleton
 * rows while loading, and a pagination footer.
 *
 * Deliberate choices:
 * - Column definitions, not a table library. The backend paginates and does
 *   not sort, so client-side sorting would only sort the current page and
 *   quietly lie about the rest.
 * - Mobile-first: low-value columns declare `hideBelow`, so a clerk on a
 *   phone gets a narrow, readable table instead of a horizontally scrolling
 *   spreadsheet.
 * - Money and quantities are rendered by the caller (right-aligned numeric
 *   columns use `tabular-nums` so digits line up down the column).
 */
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/utils'

import { Button } from './Button'
import { EmptyState } from './EmptyState'
import { ErrorState } from './Loading'

type Align = 'left' | 'center' | 'right'
type Breakpoint = 'sm' | 'md' | 'lg' | 'xl'

export interface DataColumn<T> {
  key: string
  header: React.ReactNode
  render: (row: T) => React.ReactNode
  align?: Align
  /** Extra classes for the body cell (header stays aligned and small). */
  className?: string
  /** Drop this column below the given breakpoint. */
  hideBelow?: Breakpoint
}

const ALIGN_CELL: Record<Align, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right tabular-nums',
}

const HIDE_BELOW: Record<Breakpoint, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
  xl: 'hidden xl:table-cell',
}

export interface DataTablePagination {
  limit: number
  offset: number
  total: number
  onChange: (offset: number) => void
  /** Shows the "Rows per page" control when both options and a handler are given. */
  pageSizeOptions?: number[]
  onPageSizeChange?: (limit: number) => void
}

/**
 * Page numbers with single-page gaps, identical to the ICRMS table:
 * always first and last, a sliding window around the current page, and an
 * ellipsis wherever numbers were skipped.
 */
function getPageNumbers(current: number, total: number): (number | 'ellipsis')[] {
  const pages: (number | 'ellipsis')[] = []
  const start = Math.max(2, current - 1)
  const end = Math.min(total - 1, current + 1)

  pages.push(1)
  if (start > 2) pages.push('ellipsis')
  for (let i = start; i <= end; i += 1) pages.push(i)
  if (end < total - 1) pages.push('ellipsis')
  if (total > 1) pages.push(total)
  return pages
}

export interface DataTableProps<T> {
  /** Screen-reader caption for the table. */
  ariaLabel: string
  columns: DataColumn<T>[]
  /** `undefined` while the first page loads. */
  rows: T[] | undefined
  rowKey: (row: T) => string
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  /** Makes the whole row navigate. Cells can still hold their own links. */
  rowHref?: (row: T) => string
  empty: { title: string; description?: string }
  toolbar?: React.ReactNode
  pagination?: DataTablePagination
}

const SKELETON_ROWS = 6

export function DataTable<T>({
  ariaLabel,
  columns,
  rows,
  rowKey,
  loading = false,
  error,
  onRetry,
  rowHref,
  empty,
  toolbar,
  pagination,
}: DataTableProps<T>) {
  const navigate = useNavigate()

  const page = pagination
    ? Math.floor(pagination.offset / pagination.limit) + 1
    : 1
  const pageCount = pagination
    ? Math.max(1, Math.ceil(pagination.total / pagination.limit))
    : 1
  const from = !pagination || pagination.total === 0 ? 0 : pagination.offset + 1
  const to = pagination
    ? Math.min(pagination.offset + pagination.limit, pagination.total)
    : 0

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      {toolbar && (
        <div className="flex flex-col gap-2 border-b border-gray-200 bg-white p-3 sm:flex-row sm:items-center">
          {toolbar}
        </div>
      )}

      {error ? (
        <div className="p-4">
          <ErrorState message={error} onRetry={onRetry} />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">{ariaLabel}</caption>
            <thead>
              <tr className="bg-gray-50">
                {columns.map((col) => (
                  <th
                    key={col.key}
                    scope="col"
                    className={cn(
                      'px-4 py-2.5 text-xs font-semibold tracking-wide text-gray-500 uppercase',
                      ALIGN_CELL[col.align ?? 'left'],
                      col.hideBelow && HIDE_BELOW[col.hideBelow],
                    )}
                  >
                    {col.header}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {loading ? (
                Array.from({ length: SKELETON_ROWS }).map((_, rowIndex) => (
                  <tr key={`skeleton-${rowIndex}`} className="border-t border-gray-200">
                    {columns.map((col) => (
                      <td
                        key={col.key}
                        className={cn(
                          'px-4 py-3',
                          col.hideBelow && HIDE_BELOW[col.hideBelow],
                        )}
                      >
                        <div className="h-3 w-3/4 animate-pulse rounded bg-gray-200" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : rows && rows.length > 0 ? (
                rows.map((row) => {
                  const href = rowHref?.(row)
                  return (
                    <tr
                      key={rowKey(row)}
                      onClick={href ? () => navigate(href) : undefined}
                      onKeyDown={
                        href
                          ? (event) => {
                              if (event.key === 'Enter' || event.key === ' ') {
                                event.preventDefault()
                                navigate(href)
                              }
                            }
                          : undefined
                      }
                      tabIndex={href ? 0 : undefined}
                      className={cn(
                        'border-t border-gray-200 transition-colors',
                        href &&
                          'cursor-pointer hover:bg-gray-50 focus-visible:bg-gray-50 focus-visible:outline-none',
                      )}
                    >
                      {columns.map((col) => (
                        <td
                          key={col.key}
                          className={cn(
                            'px-4 py-3 align-middle text-gray-900',
                            ALIGN_CELL[col.align ?? 'left'],
                            col.hideBelow && HIDE_BELOW[col.hideBelow],
                            col.className,
                          )}
                        >
                          {col.render(row)}
                        </td>
                      ))}
                    </tr>
                  )
                })
              ) : (
                <tr className="border-t border-gray-200">
                  <td colSpan={columns.length} className="p-0">
                    <EmptyState
                      bordered={false}
                      title={empty.title}
                      description={empty.description}
                    />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {pagination && !error && (
        <div className="flex flex-col gap-3 border-t border-gray-200 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-gray-600">
            Showing {from} to {to} of {pagination.total.toLocaleString()}{' '}
            entries
          </p>

          <div className="flex items-center gap-4">
            {pagination.pageSizeOptions && pagination.onPageSizeChange && (
              <div className="hidden items-center gap-2 sm:flex">
                <label
                  htmlFor="data-table-page-size"
                  className="text-sm text-gray-600"
                >
                  Rows per page
                </label>
                <select
                  id="data-table-page-size"
                  value={pagination.limit}
                  onChange={(e) =>
                    pagination.onPageSizeChange?.(Number(e.target.value))
                  }
                  className="h-8 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-700 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 focus:outline-none"
                >
                  {pagination.pageSizeOptions.map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex items-center gap-1">
              <Button
                size="sm"
                className="h-8 w-8 px-0"
                aria-label="Previous page"
                disabled={pagination.offset === 0}
                onClick={() =>
                  pagination.onChange(
                    Math.max(0, pagination.offset - pagination.limit),
                  )
                }
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>

              {getPageNumbers(page, pageCount).map((entry, index) =>
                entry === 'ellipsis' ? (
                  <span
                    key={`ellipsis-${index}`}
                    className="px-1.5 text-sm text-gray-500"
                  >
                    …
                  </span>
                ) : (
                  <Button
                    key={entry}
                    size="sm"
                    variant={entry === page ? 'primary' : 'secondary'}
                    className="h-8 w-8 px-0 text-sm"
                    aria-label={`Page ${entry}`}
                    aria-current={entry === page ? 'page' : undefined}
                    onClick={() =>
                      pagination.onChange((entry - 1) * pagination.limit)
                    }
                  >
                    {entry}
                  </Button>
                ),
              )}

              <Button
                size="sm"
                className="h-8 w-8 px-0"
                aria-label="Next page"
                disabled={
                  pagination.offset + pagination.limit >= pagination.total
                }
                onClick={() =>
                  pagination.onChange(pagination.offset + pagination.limit)
                }
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
