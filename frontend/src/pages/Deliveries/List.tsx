import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { ExportButton } from '@/components/common/ExportButton'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useDeliveries } from '@/hooks/useDeliveries'
import { formatMoney } from '@/lib/auth'
import { formatDate } from '@/lib/datetime'
import type { Delivery } from '@/types/api'

const DEFAULT_PAGE_SIZE = 10
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

/** 100.0000 → "100", 12.5000 → "12.5". Quantities are 4dp in the DB. */
function formatQuantity(quantity: string): string {
  return Number(quantity).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  })
}

const columns: DataColumn<Delivery>[] = [
  {
    key: 'date',
    header: 'Delivered',
    hideBelow: 'md',
    render: (d) => (
      <span className="text-stone-600 tabular-nums">
        {formatDate(d.delivered_at)}
      </span>
    ),
  },
  {
    key: 'farmer',
    header: 'Farmer',
    render: (d) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-foreground">{d.farmer_name}</div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground md:hidden">
          {formatDate(d.delivered_at)} ·{' '}
          {d.produce_line_name}
        </div>
      </div>
    ),
  },
  {
    key: 'produce',
    header: 'Produce line',
    hideBelow: 'md',
    render: (d) => <span className="text-stone-600">{d.produce_line_name}</span>,
  },
  {
    key: 'quantity',
    header: 'Quantity',
    align: 'right',
    hideBelow: 'sm',
    render: (d) => (
      <span
        className={
          d.reversal_of_id
            ? 'font-medium text-danger-ink'
            : 'text-foreground'
        }
      >
        {formatQuantity(d.quantity)}
      </span>
    ),
  },
  {
    key: 'amount',
    header: 'Amount',
    align: 'right',
    render: (d) =>
      d.amount === null ? (
        <span className="text-stone-300">—</span>
      ) : (
        <span
          className={`font-medium ${
            Number(d.amount) < 0 ? 'text-danger-ink' : 'text-foreground'
          }`}
        >
          {formatMoney(d.amount, d.currency_snapshot)}
        </span>
      ),
  },
  {
    key: 'status',
    header: 'Status',
    hideBelow: 'sm',
    render: (d) =>
      d.reversal_of_id ? (
        <StatusBadge tone="danger">Reversal</StatusBadge>
      ) : d.rate_snapshot === null ? (
        <StatusBadge tone="warning">Pending rate</StatusBadge>
      ) : (
        <StatusBadge tone="success">Valued</StatusBadge>
      ),
  },
]

export default function DeliveriesList() {
  const [searchParams] = useSearchParams()
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  // The dashboard links here with ?unvalued=1 to review pending records.
  const [unvaluedOnly, setUnvaluedOnly] = useState(
    searchParams.get('unvalued') === '1',
  )
  const [includeReversals, setIncludeReversals] = useState(false)

  const { data, isLoading, error, refetch } = useDeliveries({
    limit: pageSize,
    offset,
    unvalued_only: unvaluedOnly || undefined,
    include_reversals: includeReversals || undefined,
  })

  return (
    <div>
      <PageHeader
        title="Deliveries"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'record' : 'records'}`
            : 'Loading deliveries…'
        }
        action={
          <ButtonLink
            to="/deliveries/new"
            variant="primary"
            icon={<Plus className="h-4 w-4" />}
          >
            Record delivery
          </ButtonLink>
        }
      />

      <DataTable
        ariaLabel="Recorded deliveries"
        columns={columns}
        rows={data?.items}
        rowKey={(d) => d.id}
        rowHref={(d) => `/deliveries/${d.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No deliveries recorded',
          description: unvaluedOnly
            ? 'Nothing is awaiting valuation.'
            : 'Record the first delivery to get started.',
        }}
        toolbar={
          <>
            <label className="inline-flex cursor-pointer items-center gap-2 text-[13px] text-stone-600">
              <input
                type="checkbox"
                checked={unvaluedOnly}
                onChange={(e) => {
                  setUnvaluedOnly(e.target.checked)
                  setOffset(0)
                }}
                className="h-3.5 w-3.5 rounded border-stone-300 accent-primary-600"
              />
              Pending valuation only
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
              path="/deliveries/export"
              params={{
                unvalued_only: unvaluedOnly || undefined,
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
