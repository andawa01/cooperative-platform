import { useState } from 'react'

import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { NotificationStatusBadge } from '@/components/common/StatusBadge'
import { useNotifications } from '@/hooks/useNotifications'
import type { Notification } from '@/types/api'

const DEFAULT_PAGE_SIZE = 10
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const TEMPLATE_LABELS: Record<string, string> = {
  delivery_recorded: 'Delivery',
  payment_recorded: 'Payment',
}

const columns: DataColumn<Notification>[] = [
  {
    key: 'created',
    header: 'Created',
    hideBelow: 'sm',
    render: (n) => (
      <span className="text-gray-700">
        {new Date(n.created_at).toLocaleDateString()}
      </span>
    ),
  },
  {
    key: 'recipient',
    header: 'Recipient',
    render: (n) => (
      <div className="min-w-0">
        <div className="font-medium text-gray-900 tabular-nums">
          {n.recipient}
        </div>
        <div className="mt-0.5 truncate text-xs text-gray-500 lg:hidden">
          {TEMPLATE_LABELS[n.template] ?? n.template}
        </div>
      </div>
    ),
  },
  {
    key: 'template',
    header: 'About',
    hideBelow: 'lg',
    render: (n) => (
      <span className="text-gray-700">
        {TEMPLATE_LABELS[n.template] ?? n.template}
      </span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (n) => (
      <div className="flex flex-wrap items-center gap-1.5">
        <NotificationStatusBadge status={n.status} />
        {n.attempts > 1 && (
          <span className="text-xs text-gray-500">{n.attempts} tries</span>
        )}
      </div>
    ),
  },
  {
    key: 'content',
    header: 'Message',
    hideBelow: 'xl',
    render: (n) => (
      <span className="line-clamp-2 max-w-md text-xs text-gray-600">
        {n.content}
      </span>
    ),
  },
]

export default function NotificationsList() {
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const { data, isLoading, error, refetch } = useNotifications({
    limit: pageSize,
    offset,
  })

  return (
    <div className="p-4 md:p-6">
      <PageHeader
        title="Notifications"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'message' : 'messages'} sent to farmers`
            : 'Loading notifications…'
        }
      />

      <DataTable
        ariaLabel="SMS notifications"
        columns={columns}
        rows={data?.items}
        rowKey={(n) => n.id}
        rowHref={(n) => `/notifications/${n.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No notifications yet',
          description:
            'Delivery and payment confirmations will appear here once they are sent.',
        }}
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
