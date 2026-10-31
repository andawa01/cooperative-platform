import { useState } from 'react'
import { Plus } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useProduceLines } from '@/hooks/useProduceLines'
import type { ProduceLine } from '@/types/api'

const columns: DataColumn<ProduceLine>[] = [
  {
    key: 'name',
    header: 'Produce line',
    render: (l) => (
      <div className="min-w-0">
        <div className="truncate font-medium text-gray-900">{l.name}</div>
        <div className="mt-0.5 font-mono text-xs text-gray-500">{l.code}</div>
      </div>
    ),
  },
  {
    key: 'unit',
    header: 'Priced per',
    hideBelow: 'sm',
    render: (l) => <span className="text-gray-700">{l.unit}</span>,
  },
  {
    key: 'description',
    header: 'Description',
    hideBelow: 'lg',
    render: (l) => (
      <span className="text-gray-600">{l.description ?? '—'}</span>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (l) =>
      l.is_active ? (
        <StatusBadge tone="success">Active</StatusBadge>
      ) : (
        <StatusBadge tone="neutral">Inactive</StatusBadge>
      ),
  },
]

export default function ProduceList() {
  const [includeInactive, setIncludeInactive] = useState(false)
  const { data, isLoading, error, refetch } = useProduceLines({
    include_inactive: includeInactive,
    limit: 100,
  })

  return (
    <div className="p-4 md:p-6">
      <PageHeader
        title="Produce & Rates"
        description="What the cooperative trades, and its effective-dated prices."
        action={
          <ButtonLink
            to="/produce/new"
            variant="primary"
            icon={<Plus className="h-4 w-4" />}
          >
            Add produce line
          </ButtonLink>
        }
      />

      <DataTable
        ariaLabel="Produce lines"
        columns={columns}
        rows={data?.items}
        rowKey={(l) => l.id}
        rowHref={(l) => `/produce/${l.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No produce lines',
          description: 'Add the first produce line to get started.',
        }}
        toolbar={
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            Include inactive
          </label>
        }
      />
    </div>
  )
}
