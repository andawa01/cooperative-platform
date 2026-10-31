import { useState } from 'react'
import { Plus } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { usePayments } from '@/hooks/usePayments'
import { formatMoney, parseMoney } from '@/lib/auth'
import type { Payment, PaymentMethod } from '@/types/api'

const DEFAULT_PAGE_SIZE = 10
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const METHOD_LABELS: Record<PaymentMethod, string> = {
  cash: 'Cash',
  mobile_money: 'Mobile money',
  bank_transfer: 'Bank transfer',
}

const columns: DataColumn<Payment>[] = [
  {
    key: 'date',
    header: 'Paid',
    hideBelow: 'sm',
    render: (p) => (
      <span className="text-stone-600 tabular-nums">
        {new Date(p.paid_at).toLocaleDateString()}
      </span>
    ),
  },
  {
    key: 'farmer',
    header: 'Farmer',
    render: (p) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-foreground">{p.farmer_name}</div>
        <div className="mt-0.5 truncate text-xs text-muted-foreground sm:hidden">
          {new Date(p.paid_at).toLocaleDateString()} ·{' '}
          {METHOD_LABELS[p.method] ?? p.method}
        </div>
      </div>
    ),
  },
  {
    key: 'method',
    header: 'Method',
    hideBelow: 'md',
    render: (p) => (
      <span className="text-stone-600">{METHOD_LABELS[p.method] ?? p.method}</span>
    ),
  },
  {
    key: 'reference',
    header: 'Reference',
    hideBelow: 'lg',
    render: (p) => (
      <span className="font-mono text-xs text-muted-foreground">
        {p.reference ?? '—'}
      </span>
    ),
  },
  {
    key: 'amount',
    header: 'Amount',
    align: 'right',
    render: (p) => (
      <span
        className={`font-medium ${
          Number(p.amount) < 0 ? 'text-danger-ink' : 'text-foreground'
        }`}
      >
        {formatMoney(p.amount, p.currency)}
      </span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    hideBelow: 'sm',
    render: (p) =>
      p.reversal_of_id ? (
        <StatusBadge tone="danger">Reversal</StatusBadge>
      ) : parseMoney(p.unallocated_amount) > 0 ? (
        <StatusBadge tone="info">Credit on account</StatusBadge>
      ) : (
        <StatusBadge tone="success">Settled</StatusBadge>
      ),
  },
]

export default function PaymentsList() {
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [includeReversals, setIncludeReversals] = useState(false)

  const { data, isLoading, error, refetch } = usePayments({
    limit: pageSize,
    offset,
    include_reversals: includeReversals || undefined,
  })

  return (
    <div>
      <PageHeader
        title="Payments"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'payment' : 'payments'}`
            : 'Loading payments…'
        }
        action={
          <ButtonLink
            to="/payments/new"
            variant="primary"
            icon={<Plus className="h-4 w-4" />}
          >
            Record payment
          </ButtonLink>
        }
      />

      <DataTable
        ariaLabel="Recorded payments"
        columns={columns}
        rows={data?.items}
        rowKey={(p) => p.id}
        rowHref={(p) => `/payments/${p.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No payments recorded',
          description: 'Record the first payment to get started.',
        }}
        toolbar={
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
