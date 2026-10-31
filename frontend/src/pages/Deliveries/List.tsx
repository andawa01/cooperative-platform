import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Plus } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useDeliveries } from '@/hooks/useDeliveries'
import { formatMoney } from '@/lib/auth'
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
      <span className="text-gray-700">
        {new Date(d.delivered_at).toLocaleDateString()}
      </span>
    ),
  },
  {
    key: 'farmer',
    header: 'Farmer',
    render: (d) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-gray-900">{d.farmer_name}</div>
        <div className="mt-0.5 truncate text-xs text-gray-500 md:hidden">
          {new Date(d.delivered_at).toLocaleDateString()} ·{' '}
          {d.produce_line_name}
        </div>
      </div>
    ),
  },
  {
    key: 'produce',
    header: 'Produce line',
    hideBelow: 'md',
    render: (d) => (
      <span className="text-gray-700">{d.produce_line_name}</span>
    ),
  },
  {
    key: 'quantity',
    header: 'Quantity',
    align: 'right',
    hideBelow: 'sm',
    render: (d) => (
      <span
        className={
          d.reversal_of_id ? 'font-medium text-red-700' : 'text-gray-900'
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
        <span className="text-gray-400">—</span>
      ) : (
        <span
          className={`font-medium ${
            Number(d.amount) < 0 ? 'text-red-700' : 'text-gray-900'
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
    <div className="p-4 md:p-6">
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
            <label className="inline-flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={unvaluedOnly}
                onChange={(e) => {
                  setUnvaluedOnly(e.target.checked)
                  setOffset(0)
                }}
                className="h-4 w-4 rounded border-gray-300"
              />
              Pending valuation only
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={includeReversals}
                onChange={(e) => {
                  setIncludeReversals(e.target.checked)
                  setOffset(0)
                }}
                className="h-4 w-4 rounded border-gray-300"
              />
              Include reversals
            </label>
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
