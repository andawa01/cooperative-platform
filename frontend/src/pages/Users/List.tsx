/**
 * User management.
 *
 * Before this screen, a role could only be chosen at registration and there
 * was no way to deactivate an account at all. Both now happen here, with two
 * guards enforced by the API: you cannot change your own role, and you cannot
 * remove the last active administrator.
 */
import { useEffect, useState } from 'react'
import { Search, UserPlus } from 'lucide-react'

import { Button, ButtonLink } from '@/components/common/Button'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import { useUpdateUser, useUsers } from '@/hooks/useUsers'
import type { User, UserRole } from '@/types/api'

const DEFAULT_PAGE_SIZE = 10
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

export default function UsersList() {
  const { user: me } = useAuth()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [actionError, setActionError] = useState<string | null>(null)

  // 300ms debounce, matching the farmers list.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search)
      setOffset(0)
    }, 300)
    return () => clearTimeout(timer)
  }, [search])

  const { data, isLoading, error, refetch } = useUsers({
    limit: pageSize,
    offset,
    ...(debouncedSearch ? { search: debouncedSearch } : {}),
  })
  const update = useUpdateUser()

  const applyChange = async (id: string, body: Parameters<typeof update.mutate>[0]['body']) => {
    setActionError(null)
    try {
      await update.mutateAsync({ id, body })
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  const requestToggle = (user: User) => {
    // Deactivating signs the person out immediately, which is disruptive
    // enough to confirm — the same rule the farmer archive action follows.
    if (
      user.is_active &&
      !confirm(`Deactivate ${user.full_name}? They are signed out now.`)
    ) {
      return
    }
    applyChange(user.id, { is_active: !user.is_active })
  }

  const columns: DataColumn<User>[] = [
    {
      key: 'user',
      header: 'Account',
      render: (user) => {
        const isSelf = user.id === me?.id
        return (
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="truncate font-medium text-foreground">
                {user.full_name}
              </span>
              {isSelf && (
                <span className="text-[11px] text-muted-foreground">(you)</span>
              )}
            </div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {user.email}
            </div>

            {/*
              Phones: a fourth column does not fit here, and putting the
              action in it clipped the button off the right edge. State and
              action move into this cell instead, which always has room.
            */}
            <div className="mt-2 flex items-center gap-2 sm:hidden">
              {user.is_active ? (
                <StatusBadge tone="success">Active</StatusBadge>
              ) : (
                <StatusBadge tone="neutral">Deactivated</StatusBadge>
              )}
              <Button
                size="sm"
                variant={user.is_active ? 'danger' : 'secondary'}
                disabled={isSelf || update.isPending}
                onClick={() => requestToggle(user)}
              >
                {user.is_active ? 'Deactivate' : 'Reactivate'}
              </Button>
            </div>
          </div>
        )
      },
    },
    {
      key: 'role',
      header: 'Role',
      render: (user) => (
        <select
          value={user.role}
          aria-label={`Role for ${user.full_name}`}
          disabled={user.id === me?.id || update.isPending}
          onChange={(event) =>
            applyChange(user.id, { role: event.target.value as UserRole })
          }
          className="h-8 cursor-pointer rounded-lg border border-input bg-card px-2 text-[13px] text-stone-700 shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="clerk">Clerk</option>
          <option value="admin">Admin</option>
        </select>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      hideBelow: 'sm',
      render: (user) =>
        user.is_active ? (
          <StatusBadge tone="success">Active</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">Deactivated</StatusBadge>
        ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      // Phones render this action inside the account cell instead.
      hideBelow: 'sm',
      render: (user) => (
        <Button
          size="sm"
          variant={user.is_active ? 'danger' : 'secondary'}
          disabled={user.id === me?.id || update.isPending}
          onClick={() => requestToggle(user)}
        >
          {user.is_active ? 'Deactivate' : 'Reactivate'}
        </Button>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Users"
        description={
          data
            ? `${data.total} ${data.total === 1 ? 'account' : 'accounts'} with access to this co-op`
            : 'Loading accounts…'
        }
        action={
          <ButtonLink
            to="/users/new"
            variant="primary"
            icon={<UserPlus className="h-4 w-4" />}
          >
            New user
          </ButtonLink>
        }
      />

      {actionError && (
        <div
          role="alert"
          className="mb-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink"
        >
          {actionError}
        </div>
      )}

      <DataTable
        ariaLabel="User accounts"
        columns={columns}
        rows={data?.items}
        rowKey={(user) => user.id}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        empty={{
          title: 'No accounts found',
          description: debouncedSearch
            ? 'Try a different name or email.'
            : 'Create the first account to get started.',
        }}
        toolbar={
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-stone-400" />
            <input
              type="search"
              placeholder="Search by name or email…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="h-9 w-full rounded-lg border border-input bg-card pr-3 pl-9 text-sm shadow-xs transition-[border-color,box-shadow] placeholder:text-stone-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
            />
          </div>
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

      <p className="mt-3 text-xs text-muted-foreground">
        Deactivating an account signs it out immediately — its existing tokens
        stop working rather than waiting to expire.
      </p>
    </div>
  )
}
