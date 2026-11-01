import { useEffect, useState } from 'react'
import { Plus, Search } from 'lucide-react'

import { ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { FarmerStatusBadge } from '@/components/common/StatusBadge'
import { Avatar } from '@/components/common/Avatar'
import { ExportButton } from '@/components/common/ExportButton'
import { useFarmers, type FarmerListParams } from '@/hooks/useFarmers'
import type { Farmer } from '@/types/api'

const DEFAULT_PAGE_SIZE = 10
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const columns: DataColumn<Farmer>[] = [
  {
    key: 'name',
    header: 'Farmer',
    render: (f) => (
      <div className="flex min-w-0 items-center gap-3">
        <Avatar first={f.first_name} last={f.last_name} />
        <div className="min-w-0">
          <div className="truncate font-medium text-foreground">
            {f.first_name} {f.last_name}
          </div>
          {/* Phone repeats under the name only where the phone column is hidden. */}
          <div className="mt-0.5 truncate text-xs text-muted-foreground tabular-nums md:hidden">
            {f.phone}
          </div>
        </div>
      </div>
    ),
  },
  {
    key: 'phone',
    header: 'Phone',
    hideBelow: 'md',
    render: (f) => (
      <span className="text-stone-600 tabular-nums">{f.phone}</span>
    ),
  },
  {
    key: 'location',
    header: 'Location',
    hideBelow: 'lg',
    render: (f) => <span className="text-stone-600">{f.location ?? '—'}</span>,
  },
  {
    key: 'status',
    header: 'Status',
    render: (f) => <FarmerStatusBadge status={f.status} />,
  },
]

export default function FarmersList() {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

  // 300ms debounce so typing does not fire a request per keystroke.
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setOffset(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  const params: FarmerListParams = {
    limit: pageSize,
    offset,
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
    ...(status ? { status } : {}),
  }

  const { data, isLoading, error, refetch } = useFarmers(params)

  return (
    <div>
      <PageHeader
        title="Farmers"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'farmer' : 'farmers'} registered`
            : 'Loading farmers…'
        }
        action={
          <ButtonLink
            to="/farmers/new"
            variant="primary"
            icon={<Plus className="h-4 w-4" />}
          >
            Register farmer
          </ButtonLink>
        }
      />

      <DataTable
        ariaLabel="Registered farmers"
        columns={columns}
        rows={data?.items}
        rowKey={(f) => f.id}
        rowHref={(f) => `/farmers/${f.id}`}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No farmers found',
          description:
            debouncedSearch || status
              ? 'Try a different search or clear the filter.'
              : 'Register your first farmer to get started.',
        }}
        toolbar={
          <>
            <div className="relative flex-1 sm:max-w-xs">
              <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-stone-400" />
              <input
                type="search"
                placeholder="Search by name or phone…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-9 w-full rounded-lg border border-input bg-card pr-3 pl-9 text-sm shadow-xs transition-[border-color,box-shadow] placeholder:text-stone-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
              />
            </div>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value)
                setOffset(0)
              }}
              aria-label="Filter by status"
              className="h-9 cursor-pointer rounded-lg border border-input bg-card px-3 text-sm text-stone-700 shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="pending_verification">Pending</option>
              <option value="suspended">Suspended</option>
              <option value="archived">Archived</option>
            </select>
            <ExportButton
              className="sm:ml-auto"
              path="/farmers/export"
              params={{
                search: debouncedSearch || undefined,
                status: status || undefined,
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
