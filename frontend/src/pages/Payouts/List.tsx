import { useState } from 'react'
import { Plus } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import { usePayoutRuns } from '@/hooks/usePayouts'
import { formatMoney } from '@/lib/auth'
import { formatDateTime } from '@/lib/datetime'
import type { PayoutBatch, PayoutStatus } from '@/types/api'

const PAGE_SIZE = 20

const STATUS: Record<
  PayoutStatus,
  { label: string; tone: 'neutral' | 'success' | 'warning' | 'danger' | 'info' }
> = {
  draft: { label: 'Draft', tone: 'warning' },
  approved: { label: 'Approved', tone: 'info' },
  dispatched: { label: 'Dispatched', tone: 'success' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

const columns: DataColumn<PayoutBatch>[] = [
  {
    key: 'reference',
    header: 'Run',
    render: (run) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-foreground">
          {run.reference ?? '—'}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground tabular-nums">
          {formatDateTime(run.created_at)}
        </div>
      </div>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    hideBelow: 'sm',
    render: (run) => {
      const meta = STATUS[run.status] ?? { label: run.status, tone: 'neutral' }
      return <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>
    },
  },
  {
    key: 'members',
    header: 'Members',
    align: 'right',
    hideBelow: 'md',
    render: (run) => (
      <span className="text-stone-600 tabular-nums">
        {run.paid_count}/{run.item_count} paid
      </span>
    ),
  },
  {
    key: 'total',
    header: 'Total',
    align: 'right',
    render: (run) => (
      <div>
        <div className="font-medium text-foreground">
          {formatMoney(run.total_amount, run.currency)}
        </div>
        {run.failed_count > 0 && (
          <div className="mt-0.5 text-xs font-medium text-danger-ink">
            {run.failed_count} failed
          </div>
        )}
      </div>
    ),
  },
]

export default function PayoutRunsList() {
  const { isAdmin } = useAuth()
  const [offset, setOffset] = useState(0)
  const { data, isLoading, error, refetch } = usePayoutRuns({
    limit: PAGE_SIZE,
    offset,
  })

  return (
    <div>
      <PageHeader
        title="Payout runs"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'run' : 'runs'} — each one pays every included member from a single approval`
            : 'Loading payout runs…'
        }
        action={
          isAdmin ? (
            <ButtonLink
              to="/payouts/new"
              variant="primary"
              icon={<Plus className="h-4 w-4" />}
            >
              New run
            </ButtonLink>
          ) : undefined
        }
      />

      <DataTable
        ariaLabel="Payout runs"
        columns={columns}
        rows={data?.items}
        rowKey={(run) => run.id}
        rowHref={(run) => `/payouts/${run.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No payout runs yet',
          description:
            'A run collects every member with a positive payable into one approval, then pays them together.',
        }}
        pagination={{
          limit: PAGE_SIZE,
          offset,
          total: data?.total ?? 0,
          onChange: setOffset,
        }}
      />
    </div>
  )
}
