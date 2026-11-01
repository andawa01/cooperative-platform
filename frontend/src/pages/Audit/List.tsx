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
import { Link, useSearchParams } from 'react-router-dom'

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
  'deduction.create',
  'deduction.reverse',
]

const ENTITY_TYPES = ['delivery', 'payment', 'deduction', 'rate', 'farmer', 'user']

/**
 * The verb alone. The entity column already says what was acted on, so
 * "rate.create" under "Maize — 120 KES/kg" reads as a stutter; "Create"
 * reads as a sentence. Full technical names live in the filter dropdown and
 * in the tooltip, for the rare reader who needs the exact action string.
 */
const ACTION_LABELS: Record<string, string> = {
  'delivery.create': 'Create',
  'delivery.value': 'Valued',
  'delivery.reverse': 'Reversal',
  'payment.create': 'Create',
  'payment.reverse': 'Reversal',
  'rate.create': 'Create',
  'farmer.create': 'Create',
  'farmer.update': 'Updated',
  'farmer.verify': 'Verified',
  'farmer.archive': 'Archived',
  'user.create': 'Create',
  'user.update': 'Updated',
  'user.password_change': 'Password change',
  'deduction.create': 'Create',
  'deduction.reverse': 'Reversal',
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

function actionTone(action: string): 'success' | 'danger' | 'info' | 'warning' | 'neutral' {
  if (action.endsWith('.reverse')) return 'danger'
  if (action.endsWith('.create')) return 'success'
  if (action.endsWith('.verify')) return 'success'
  if (action.endsWith('.value')) return 'info'
  if (action.endsWith('.update')) return 'info'
  if (action.endsWith('.password_change')) return 'warning'
  return 'neutral'
}

/**
 * Where a change happened, in clickable form.
 *
 * Not every entity has its own screen: rates live inside a produce line and a
 * user is managed from the users list, so those return undefined and the row
 * simply does not navigate. A dead link would be worse than no link.
 */
function recordPath(entry: AuditEntry): string | undefined {
  switch (entry.entity_type) {
    case 'delivery':
      return `/deliveries/${entry.entity_id}`
    case 'payment':
      return `/payments/${entry.entity_id}`
    case 'deduction':
      return `/deductions/${entry.entity_id}`
    case 'farmer':
      return `/farmers/${entry.entity_id}`
    default:
      return undefined
  }
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
        <span title={entry.action}>
          <StatusBadge tone={actionTone(entry.action)} dot={false}>
            {actionLabel(entry.action)}
          </StatusBadge>
        </span>
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
    hideBelow: 'sm',
    // The name, and nothing else. An id on the row is noise a manager cannot
    // act on; the id lives in the expanded panel for whoever needs to
    // cross-reference a record.
    render: (entry) => {
      const path = recordPath(entry)
      return (
      <div className="min-w-0">
        {entry.entity_label ? (
          path ? (
            <Link
              to={path}
              className="block truncate text-stone-700 hover:text-primary-ink hover:underline"
            >
              {entry.entity_label}
            </Link>
          ) : (
            <div className="truncate text-stone-700">{entry.entity_label}</div>
          )
        ) : (
          <div className="truncate text-muted-foreground italic">
            record no longer exists
          </div>
        )}
        <div className="mt-0.5 text-[11px] text-muted-foreground capitalize">
          {entry.entity_type}
        </div>
      </div>
      )
    },
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
          <div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Snapshot label="Before" value={entry.before} />
              <Snapshot label="After" value={entry.after} />
            </div>
            {/* Machine identifiers belong here, not on the row: an auditor
                may need to match a request against a server log, and nobody
                else ever reads these. */}
            <div className="mt-3 flex flex-col gap-1 border-t border-border/60 pt-2.5 text-[11px] text-muted-foreground sm:flex-row sm:gap-6">
              <span>
                Record{' '}
                <span className="font-mono">{entry.entity_id}</span>
              </span>
              <span>
                Request{' '}
                <span className="font-mono">{entry.request_id ?? '—'}</span>
              </span>
            </div>
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
                Filtered to a single record
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
