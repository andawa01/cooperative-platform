import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Loader2, Link2, ShieldCheck, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/common/Button'
import { Card, CardBody } from '@/components/common/Card'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import { useApprovals, useDecideApproval } from '@/hooks/useApprovals'
import { formatMoney } from '@/lib/auth'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type { Approval, ApprovalStatus } from '@/types/api'

const ACTION_LABEL: Record<string, string> = {
  'payment.reverse': 'Reverse payment',
  'deduction.reverse': 'Reverse deduction',
  'payout.dispatch': 'Dispatch payout run',
}

const STATUS_META: Record<
  ApprovalStatus,
  { label: string; tone: 'warning' | 'success' | 'danger' }
> = {
  pending: { label: 'Waiting', tone: 'warning' },
  approved: { label: 'Approved', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'danger' },
}

/**
 * The queue for money moves one admin should not make alone (D-038).
 *
 * Two behaviours matter here:
 * - Your own request has no Approve button. The server refuses it anyway
 *   (and the database does too), but a button that always fails is a worse
 *   explanation than no button.
 * - Approving executes the action immediately. That is why the row shows the
 *   amount and the one-line summary the requester saw, captured when asked —
 *   not a live recalculation of the member's balance.
 */
export default function ApprovalsList() {
  const { user } = useAuth()
  const [filter, setFilter] = useState<ApprovalStatus>('pending')
  const approvals = useApprovals({ status: filter, limit: 100 })
  const decide = useDecideApproval()

  if (approvals.isLoading) return <Loading />
  if (approvals.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(approvals.error as Error).message}
          onRetry={() => approvals.refetch()}
        />
      </div>
    )

  const items = approvals.data?.items ?? []
  const total = approvals.data?.total ?? 0

  const act = async (approval: Approval, approve: boolean) => {
    let note: string | null = null
    if (approve) {
      note = prompt(
        'Optional note for the audit trail (what you checked):',
        '',
      )
      if (note === null) return
    } else {
      note = prompt('Why are you rejecting this? (shown to the requester)')
      if (!note || note.trim().length === 0) return
    }

    try {
      await decide.mutateAsync({
        id: approval.id,
        approve,
        note: note?.trim() || null,
      })
      toast.success(approve ? 'Approved and executed' : 'Request rejected', {
        description: approve
          ? 'The action was recorded with you as the admin who released it.'
          : 'Nothing was changed. The requester can see your note.',
      })
    } catch (err) {
      toast.error('Could not record the decision', {
        description: (err as Error).message,
      })
    }
  }

  return (
    <div>
      <PageHeader
        title="Approvals"
        description="Money moves at or above the maker-checker limit wait here for a second admin. Approving executes the action; rejecting changes nothing."
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(Object.keys(STATUS_META) as ApprovalStatus[]).map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setFilter(status)}
            aria-pressed={filter === status}
            className={cn(
              'rounded-full border px-3 py-1.5 text-[13px] font-medium transition-colors',
              filter === status
                ? 'border-primary-600/30 bg-primary-soft text-primary-ink'
                : 'border-border bg-card text-stone-600 hover:bg-stone-50',
            )}
          >
            {STATUS_META[status].label}
            {status === 'pending' && filter === 'pending' && total > 0 && (
              <span className="ml-1.5 tabular-nums">({total})</span>
            )}
          </button>
        ))}
      </div>

      {items.length === 0 ? (
        <Card>
          <CardBody>
            <div className="flex flex-col items-center gap-2 py-12 text-center">
              <span className="flex h-10 w-10 items-center justify-center rounded-full bg-stone-100 text-stone-500">
                <ShieldCheck className="h-5 w-5" />
              </span>
              <p className="text-sm font-medium text-foreground">
                {filter === 'pending'
                  ? 'Nothing waiting for a second admin'
                  : `No ${filter} requests`}
              </p>
              <p className="max-w-sm text-sm text-stone-500">
                {filter === 'pending'
                  ? 'Large reversals and payout dispatches appear here when an admin asks for approval.'
                  : 'Decided requests stay here as a record of who approved what.'}
              </p>
            </div>
          </CardBody>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((approval) => {
            const meta = STATUS_META[approval.status]
            const mine = approval.requested_by_id === user?.id
            const pending = approval.status === 'pending'
            return (
              <Card key={approval.id}>
                <CardBody className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                        {ACTION_LABEL[approval.action] ?? approval.action}
                      </span>
                      <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>
                    </div>
                    <div className="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <span className="text-sm font-medium text-foreground">
                        {approval.summary}
                      </span>
                      {approval.amount && (
                        <span className="text-sm font-semibold text-foreground tabular-nums">
                          {formatMoney(
                            approval.amount,
                            approval.currency ?? 'KES',
                          )}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Asked by {approval.requested_by_name} ·{' '}
                      {formatDateTime(approval.created_at)}
                      {approval.reason ? ` · “${approval.reason}”` : ''}
                    </div>
                    {approval.decided_at && (
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {meta.label} by {approval.decided_by_name ?? 'a removed user'} ·{' '}
                        {formatDateTime(approval.decided_at)}
                        {approval.decision_note
                          ? ` · “${approval.decision_note}”`
                          : ''}
                      </div>
                    )}
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Link
                      to={`/${approval.entity_type === 'payout' ? 'payouts' : `${approval.entity_type}s`}/${approval.entity_id}`}
                      className="inline-flex items-center gap-1 text-[13px] font-medium text-primary-ink hover:underline"
                    >
                      <Link2 className="h-3.5 w-3.5" />
                      Open
                    </Link>
                    {pending && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => act(approval, true)}
                          disabled={decide.isPending || mine}
                          title={
                            mine
                              ? 'A different admin must approve this request'
                              : undefined
                          }
                        >
                          {decide.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Check className="h-3.5 w-3.5" />
                          )}
                          {mine ? 'Needs another admin' : 'Approve'}
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => act(approval, false)}
                          disabled={decide.isPending || mine}
                        >
                          <X className="h-3.5 w-3.5" />
                          Reject
                        </Button>
                      </>
                    )}
                  </div>
                </CardBody>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
