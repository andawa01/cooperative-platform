import { useState } from 'react'
import { Plus } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { ExportButton } from '@/components/common/ExportButton'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useDeductions } from '@/hooks/useDeductions'
import { formatMoney } from '@/lib/auth'
import { formatDate } from '@/lib/datetime'
import { DEDUCTION_REASONS, reasonLabel } from '@/lib/deductions'
import type { Deduction } from '@/types/api'

const DEFAULT_PAGE_SIZE = 10
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const columns: DataColumn<Deduction>[] = [
  {
    key: 'date',
    header: 'Applied',
    hideBelow: 'sm',
    render: (d) => (
      <span className="text-stone-600 tabular-nums">
        {formatDate(d.applied_at)}
      </span>
    ),
  },
  {
    key: 'farmer',
    header: 'Farmer',
    render: (d) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-foreground">{d.farmer_name}</div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground sm:hidden">
          {formatDate(d.applied_at)} · {reasonLabel(d.reason_code)}
        </div>
      </div>
    ),
  },
  {
    key: 'reason',
    header: 'Reason',
    hideBelow: 'md',
    render: (d) => (
      <span className="text-stone-600">{reasonLabel(d.reason_code)}</span>
    ),
  },
  {
    key: 'reference',
    header: 'Reference',
    hideBelow: 'lg',
    render: (d) => (
      <span className="font-mono text-xs text-muted-foreground">
        {d.reference ?? '—'}
      </span>
    ),
  },
  {
    key: 'amount',
    header: 'Withheld',
    align: 'right',
    render: (d) => (
      <span
        className={
          d.reversal_of_id
            ? 'font-medium text-success-ink tabular-nums'
            : 'font-medium text-foreground tabular-nums'
        }
      >
        {formatMoney(d.amount, d.currency)}
      </span>
    ),
  },
  {
    key: 'state',
    header: 'Status',
    hideBelow: 'sm',
    // The reversal is a separate row, so this column reads as a state rather
    // than a toggle: a charge that was withdrawn shows both lines.
    render: (d) =>
      d.reversal_of_id ? (
        <StatusBadge tone="danger">Reversal</StatusBadge>
      ) : (
        <StatusBadge tone="warning">Withheld</StatusBadge>
      ),
  },
]

export default function DeductionsList() {
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [reason, setReason] = useState('')
  const [includeReversals, setIncludeReversals] = useState(false)

  const { data, isLoading, error, refetch } = useDeductions({
    limit: pageSize,
    offset,
    reason_code: reason || undefined,
    include_reversals: includeReversals || undefined,
  })

  return (
    <div>
      <PageHeader
        title="Deductions"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'deduction' : 'deductions'}`
            : 'Loading deductions…'
        }
        action={
          <ButtonLink
            to="/deductions/new"
            variant="primary"
            icon={<Plus className="h-4 w-4" />}
          >
            Record deduction
          </ButtonLink>
        }
      />

      <DataTable
        ariaLabel="Recorded deductions"
        columns={columns}
        rows={data?.items}
        rowKey={(d) => d.id}
        rowHref={(d) => `/deductions/${d.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No deductions recorded',
          description:
            'Transport, cess and input credit are withheld here before settlement.',
        }}
        toolbar={
          <>
            <label className="inline-flex items-center gap-2 text-[13px] text-stone-600">
              <span className="sr-only">Filter by reason</span>
              <select
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value)
                  setOffset(0)
                }}
                className="h-8 rounded-md border border-input bg-card px-2 text-[13px] shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
              >
                <option value="">All reasons</option>
                {DEDUCTION_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {reasonLabel(r)}
                  </option>
                ))}
              </select>
            </label>

            <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-stone-600">
              <input
                type="checkbox"
                checked={includeReversals}
                onChange={(e) => {
                  setIncludeReversals(e.target.checked)
                  setOffset(0)
                }}
                className="h-3.5 w-3.5 rounded border-stone-300 accent-primary-600"
              />
              Include reversals
            </label>

            <ExportButton
              className="sm:ml-auto"
              path="/deductions/export"
              params={{
                reason_code: reason || undefined,
                include_reversals: includeReversals || undefined,
              }}
            />
          </>
        }
        pagination={{
          limit: pageSize,
          offset,
          total: data?.total ?? 0,
          onChange: setOffset,
          pageSizeOptions: PAGE_SIZE_OPTIONS,
          onPageSizeChange: (size) => {
            setPageSize(size)
            setOffset(0)
          },
        }}
      />
    </div>
  )
}
