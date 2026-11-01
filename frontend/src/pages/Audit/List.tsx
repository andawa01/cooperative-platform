/**
 * Audit trail.
 *
 * Read-only, admin-only, newest first. The trail already existed as an
 * endpoint; until now nobody could read it without curl, which made the
 * append-only guarantee unverifiable by the people it protects.
 *
 * Each row expands to its before/after snapshot. That detail is deliberately
 * one click away rather than a column: the payload differs per action, and a
 * list of JSON blobs is unreadable at a glance.
 */
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { ExportButton } from '@/components/common/ExportButton'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuditEntries } from '@/hooks/useAudit'
import { formatDateTime } from '@/lib/datetime'
import type { AuditEntry } from '@/types/api'

const DEFAULT_PAGE_SIZE = 20
const PAGE_SIZE_OPTIONS = [20, 50, 100]

// Mirrors AUDIT_ACTIONS in app/models/audit.py. Kept as data rather than
// derived, because the API rejects unknown values with a 422 — a stale option
// fails loudly instead of silently returning nothing.
const ACTIONS = [
  'delivery.create',
  'delivery.value',
  'delivery.reverse',
  'payment.create',
  'payment.reverse',
  'rate.create',
  'farmer.create',
  'farmer.update',
  'farmer.verify',
  'farmer.archive',
  'user.create',
  'user.update',
  'user.password_change',
]

const ENTITY_TYPES = ['delivery', 'payment', 'rate', 'farmer', 'user']

function actionTone(action: string): 'success' | 'danger' | 'info' | 'warning' | 'neutral' {
  if (action.endsWith('.reverse')) return 'danger'
  if (action.endsWith('.create')) return 'success'
  if (action.endsWith('.verify')) return 'success'
  if (action.endsWith('.value')) return 'info'
  if (action.endsWith('.update')) return 'info'
  if (action.endsWith('.password_change')) return 'warning'
  return 'neutral'
}

function Snapshot({
  label,
  value,
}: {
  label: string
  value: Record<string, unknown> | null
}) {
  return (
    <div className="min-w-0 flex-1">
      <div className="mb-1 text-[10px] font-semibold tracking-wider text-stone-500 uppercase">
        {label}
      </div>
      {value ? (
        <pre className="overflow-x-auto rounded-lg border border-border/70 bg-card p-2.5 font-mono text-[11px] leading-relaxed text-stone-700">
          {JSON.stringify(value, null, 2)}
        </pre>
      ) : (
        <p className="text-xs text-muted-foreground italic">not recorded</p>
      )}
    </div>
  )
}

const columns: DataColumn<AuditEntry>[] = [
  {
    key: 'when',
    header: 'When',
    hideBelow: 'sm',
    render: (entry) => (
      <span className="text-stone-600 tabular-nums">
        {formatDateTime(entry.created_at)}
      </span>
    ),
  },
  {
    key: 'action',
    header: 'Action',
    render: (entry) => (
      <div className="min-w-0">
        <StatusBadge tone={actionTone(entry.action)} dot={false}>
          {entry.action}
        </StatusBadge>
        <div className="mt-0.5 text-xs text-muted-foreground sm:hidden">
          {formatDateTime(entry.created_at)}
        </div>
      </div>
    ),
  },
  {
    key: 'actor',
    header: 'Actor',
    render: (entry) =>
      entry.actor_name ? (
        <span className="text-foreground">{entry.actor_name}</span>
      ) : (
        <span className="text-muted-foreground italic">system</span>
      ),
  },
  {
    key: 'entity',
    header: 'Entity',
    hideBelow: 'md',
    render: (entry) => (
      <div className="min-w-0">
        <span className="text-stone-600">{entry.entity_type}</span>
        <div className="font-mono text-[11px] text-muted-foreground">
          {entry.entity_id.slice(0, 8)}
        </div>
      </div>
    ),
  },
  {
    key: 'request',
    header: 'Request',
    hideBelow: 'xl',
    render: (entry) => (
      <span className="font-mono text-[11px] text-muted-foreground">
        {entry.request_id ?? '—'}
      </span>
    ),
  },
]

export default function AuditList() {
  const [searchParams] = useSearchParams()
  // A link from another screen may pre-filter to one record.
  const entityId = searchParams.get('entity_id') ?? undefined

  const [action, setAction] = useState(searchParams.get('action') ?? '')
  const [entityType, setEntityType] = useState(
    searchParams.get('entity_type') ?? '',
  )
  const [offset, setOffset] = useState(0)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)

  // Any filter change invalidates the current page, so the handlers below
  // reset it directly. An effect watching these values would re-render a
  // frame later and show page 3 of a filter that now has one page.
  const changeAction = (value: string) => {
    setAction(value)
    setOffset(0)
  }

  const changeEntityType = (value: string) => {
    setEntityType(value)
    setOffset(0)
  }

  const { data, isLoading, error, refetch } = useAuditEntries({
    limit: pageSize,
    offset,
    action: action || undefined,
    entity_type: entityType || undefined,
    entity_id: entityId,
  })

  return (
    <div>
      <PageHeader
        title="Audit log"
        description={
          data
            ? `${data.total.toLocaleString()} ${data.total === 1 ? 'entry' : 'entries'} — append-only, enforced by the database`
            : 'Loading the trail…'
        }
        action={
          <ExportButton
            path="/audit/export"
            params={{
              action: action || undefined,
              entity_type: entityType || undefined,
              entity_id: entityId,
            }}
          />
        }
      />

      <DataTable
        ariaLabel="Audit trail"
        columns={columns}
        rows={data?.items}
        rowKey={(entry) => entry.id}
        loading={isLoading}
        error={error ? (error as Error).message : null}
        onRetry={() => refetch()}
        renderExpanded={(entry) => (
          <div className="flex flex-col gap-3 sm:flex-row">
            <Snapshot label="Before" value={entry.before} />
            <Snapshot label="After" value={entry.after} />
          </div>
        )}
        empty={{
          title: 'No entries',
          description:
            'Nothing matches these filters. File changes, reversals and account updates all appear here.',
        }}
        toolbar={
          <>
            <select
              value={action}
              onChange={(event) => changeAction(event.target.value)}
              aria-label="Filter by action"
              className="h-9 cursor-pointer rounded-lg border border-input bg-card px-3 text-sm text-stone-700 shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
            >
              <option value="">All actions</option>
              {ACTIONS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>

            <select
              value={entityType}
              onChange={(event) => changeEntityType(event.target.value)}
              aria-label="Filter by entity type"
              className="h-9 cursor-pointer rounded-lg border border-input bg-card px-3 text-sm text-stone-700 shadow-xs focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
            >
              <option value="">All entities</option>
              {ENTITY_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>

            {entityId && (
              <span className="text-xs text-muted-foreground">
                Filtered to record{' '}
                <span className="font-mono">{entityId.slice(0, 8)}</span>
              </span>
            )}
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
