import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Ban, Check, CheckCircle2, Send } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/common/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailRow,
} from '@/components/common/Card'
import { ConfirmDialog } from '@/components/common/ConfirmDialog'
import { DataTable, type DataColumn } from '@/components/common/DataTable'
import { ExportButton } from '@/components/common/ExportButton'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import {
  useApprovePayoutRun,
  useCancelPayoutRun,
  useDispatchPayoutRun,
  usePayoutRun,
} from '@/hooks/usePayouts'
import { formatMoney } from '@/lib/auth'
import { formatDateTime } from '@/lib/datetime'
import { cn } from '@/lib/utils'
import type {
  PayoutBatch,
  PayoutItem,
  PayoutItemStatus,
  PayoutStatus,
} from '@/types/api'

type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info'

const BATCH_STATUS: Record<PayoutStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Draft', tone: 'warning' },
  approved: { label: 'Approved', tone: 'info' },
  dispatched: { label: 'Dispatched', tone: 'success' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

const ITEM_STATUS: Record<PayoutItemStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Pending', tone: 'info' },
  paid: { label: 'Paid', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

export default function PayoutRunDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const run = usePayoutRun(id)
  const approve = useApprovePayoutRun(id!)
  const dispatch = useDispatchPayoutRun(id!)
  const cancel = useCancelPayoutRun(id!)
  const [actionError, setActionError] = useState<string | null>(null)
  const [dialog, setDialog] = useState<'dispatch' | 'cancel' | null>(null)
  const [outcome, setOutcome] = useState<{
    paid: number
    failed: number
    pending: number
  } | null>(null)

  if (run.isLoading) return <Loading />
  if (run.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(run.error as Error).message}
          onRetry={() => run.refetch()}
        />
      </div>
    )
  if (!run.data) return null

  const batch = run.data
  const meta = BATCH_STATUS[batch.status] ?? {
    label: batch.status,
    tone: 'neutral' as Tone,
  }
  const canApprove = batch.status === 'draft'
  const canDispatch = batch.status === 'approved' || batch.status === 'dispatched'
  const canCancel = batch.status === 'draft' || batch.status === 'approved'
  const outstanding = batch.item_count - batch.paid_count
  const isRetry = batch.status === 'dispatched'

  const doApprove = async () => {
    setActionError(null)
    try {
      await approve.mutateAsync()
      toast.success('Run approved', {
        description: 'Nothing has been paid yet — dispatch when you are ready.',
      })
    } catch (err) {
      const message = (err as Error).message
      setActionError(message)
      toast.error('Could not approve the run', { description: message })
    }
  }

  const doDispatch = async () => {
    setActionError(null)
    setOutcome(null)
    try {
      const result = await dispatch.mutateAsync()
      setOutcome({ paid: result.paid, failed: result.failed, pending: result.pending })
      setDialog(null)
      if (result.failed > 0) {
        toast.warning('Dispatched with problems', {
          description: `${result.paid} paid, ${result.failed} failed. Fix the cause, then retry.`,
        })
      } else if (result.pending > 0) {
        toast.warning('Partly dispatched', {
          description: `${result.paid} paid, ${result.pending} still pending.`,
        })
      } else {
        toast.success('Payments recorded', {
          description: `${result.paid} member${result.paid === 1 ? '' : 's'} paid.`,
        })
      }
    } catch (err) {
      const message = (err as Error).message
      setActionError(message)
      setDialog(null)
      toast.error('Dispatch failed', { description: message })
    }
  }

  const doCancel = async () => {
    setActionError(null)
    try {
      await cancel.mutateAsync()
      setDialog(null)
      toast.success('Run cancelled', {
        description: 'Nobody was paid. Create a new run when the balances are right.',
      })
    } catch (err) {
      const message = (err as Error).message
      setActionError(message)
      setDialog(null)
      toast.error('Could not cancel the run', { description: message })
    }
  }

  const columns: DataColumn<PayoutItem>[] = [
    {
      key: 'farmer',
      header: 'Member',
      render: (item) => (
        <div className="min-w-0">
          <Link
            to={`/farmers/${item.farmer_id}`}
            className="block truncate font-medium text-foreground hover:text-primary-ink hover:underline"
          >
            {item.farmer_name}
          </Link>
          <div className="mt-0.5 text-xs text-muted-foreground tabular-nums">
            {item.phone ?? 'no phone on file'}
          </div>
        </div>
      ),
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      render: (item) => (
        <span className="font-medium text-foreground">
          {formatMoney(item.amount, item.currency)}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      hideBelow: 'sm',
      render: (item) => {
        const s = ITEM_STATUS[item.status] ?? {
          label: item.status,
          tone: 'neutral' as Tone,
        }
        return <StatusBadge tone={s.tone}>{s.label}</StatusBadge>
      },
    },
    {
      key: 'payment',
      header: 'Paid',
      hideBelow: 'md',
      render: (item) =>
        item.payment_id ? (
          <Link
            to={`/payments/${item.payment_id}`}
            className="text-stone-600 tabular-nums transition-colors hover:text-primary-ink hover:underline"
          >
            {item.dispatched_at ? formatDateTime(item.dispatched_at) : 'View payment'}
          </Link>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'error',
      header: 'Problem',
      hideBelow: 'lg',
      render: (item) =>
        item.error ? (
          <span className="text-xs text-danger-ink">{item.error}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ]

  return (
    <div>
      <PageHeader
        back={{ to: '/payouts', label: 'Payout runs' }}
        title={batch.reference ?? 'Payout run'}
        badge={<StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>}
        description={
          <>
            {batch.item_count} member{batch.item_count === 1 ? '' : 's'} ·{' '}
            {formatMoney(batch.total_amount, batch.currency)} ·{' '}
            {batch.method.replace('_', ' ')}
          </>
        }
        action={
          <>
            {batch.method === 'mobile_money' &&
              outstanding > 0 &&
              batch.status !== 'cancelled' && (
                <ExportButton
                  path={`/payout-runs/${batch.id}/rail-file`}
                  label="M-Pesa file"
                />
              )}
            <ExportButton
              path={`/payout-runs/${batch.id}/export`}
              label="Export CSV"
            />
            {isAdmin && canApprove && (
              <Button
                variant="primary"
                onClick={doApprove}
                disabled={approve.isPending}
              >
                <CheckCircle2 className="h-4 w-4" />
                {approve.isPending ? 'Approving…' : 'Approve'}
              </Button>
            )}
            {isAdmin && canDispatch && (
              <Button
                variant="primary"
                onClick={() => setDialog('dispatch')}
                disabled={dispatch.isPending}
              >
                <Send className="h-4 w-4" />
                {dispatch.isPending && !dialog
                  ? 'Paying…'
                  : isRetry
                    ? 'Retry failed'
                    : 'Dispatch'}
              </Button>
            )}
            {isAdmin && canCancel && (
              <Button
                variant="danger"
                onClick={() => setDialog('cancel')}
                disabled={cancel.isPending}
              >
                <Ban className="h-4 w-4" />
                {cancel.isPending && !dialog ? 'Cancelling…' : 'Cancel'}
              </Button>
            )}
          </>
        }
      />

      <StatusStepper status={batch.status} />

      {actionError && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
          {actionError}
        </div>
      )}

      {outcome && (
        <div
          className={`mb-4 rounded-lg border px-3 py-2.5 text-sm ${
            outcome.failed > 0
              ? 'border-warning/30 bg-warning-soft text-warning-ink'
              : 'border-success/25 bg-success-soft text-success-ink'
          }`}
        >
          {outcome.paid} paid
          {outcome.failed > 0 && `, ${outcome.failed} failed`}
          {outcome.pending > 0 && `, ${outcome.pending} still pending`}.
          {outcome.failed > 0 &&
            ' Fix the cause, then use “Retry failed” — members already paid will not be paid twice.'}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Run"
            description="Dispatching records one payment per member, with the run reference on each."
          />
          <CardBody>
            <RunProgress batch={batch} />
            <dl className="grid gap-3 sm:grid-cols-2">
              <DetailRow
                label="Total"
                value={formatMoney(batch.total_amount, batch.currency)}
              />
              <DetailRow label="Members" value={String(batch.item_count)} />
              <DetailRow label="Paid" value={String(batch.paid_count)} />
              <DetailRow
                label="Failed"
                value={
                  batch.failed_count > 0 ? (
                    <span className="text-danger-ink">{batch.failed_count}</span>
                  ) : (
                    '0'
                  )
                }
              />
              <DetailRow label="Created" value={formatDateTime(batch.created_at)} />
              <DetailRow
                label="Approved"
                value={
                  batch.approved_at ? formatDateTime(batch.approved_at) : 'Not yet'
                }
              />
              <DetailRow
                label="Dispatched"
                value={
                  batch.dispatched_at
                    ? formatDateTime(batch.dispatched_at)
                    : 'Not yet'
                }
              />
              {batch.notes && <DetailRow label="Notes" value={batch.notes} />}
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="What happens next" />
          <CardBody className="space-y-3 text-sm text-stone-600">
            {batch.method === 'cash' && (
              <p>
                Cash runs have no file. Pay against this list across the
                counter, then dispatch to record it.
              </p>
            )}
            {batch.method === 'bank_transfer' && (
              <p>
                Bank files need an account number on each member record, which
                is not captured yet. Dispatch records the transfers
                individually against this run.
              </p>
            )}
            {batch.status === 'approved' && batch.method === 'mobile_money' && (
              <p>
                Download the M-Pesa file and upload it to the portal, then
                dispatch. The file lists only members without a payment, so a
                retry can never pay someone twice.
              </p>
            )}
            {batch.status === 'draft' && (
              <p>
                An admin must approve this run before it can pay anyone. Approval
                is recorded with who did it and when.
              </p>
            )}
            {batch.status === 'approved' && batch.method !== 'mobile_money' && (
              <p>
                Dispatch records a payment for every member and queues their SMS
                advice, which states the amount sent and what was withheld.
              </p>
            )}
            {batch.status === 'dispatched' && (
              <p>
                Paid members are done. If a row failed, correct the cause and
                dispatch again — the retry never pays an already-paid member
                twice.
              </p>
            )}
            {batch.status === 'cancelled' && (
              <p>
                This run was cancelled and paid nobody. Create a new one when the
                balances are right.
              </p>
            )}
            <p className="border-t border-border/60 pt-3 text-xs text-muted-foreground">
              Money already moved is corrected by reversing the individual
              payment, not by cancelling the run.
            </p>
          </CardBody>
        </Card>
      </div>

      <div className="mt-4">
        <DataTable
          ariaLabel="Members in this payout run"
          columns={columns}
          rows={batch.items}
          rowKey={(item) => item.id}
          empty={{
            title: 'No members in this run',
            description: 'A run with no payable members is refused at creation.',
          }}
        />
      </div>

      <ConfirmDialog
        open={dialog === 'dispatch'}
        title={isRetry ? 'Retry the unpaid members?' : 'Dispatch this payout run?'}
        tone="primary"
        confirmLabel={isRetry ? 'Retry now' : 'Dispatch now'}
        busy={dispatch.isPending}
        onClose={() => setDialog(null)}
        onConfirm={doDispatch}
        description={
          <>
            <p>
              This records a real payment for{' '}
              <strong className="font-semibold text-foreground">
                {isRetry
                  ? `${outstanding} unpaid member${outstanding === 1 ? '' : 's'}`
                  : `${batch.item_count} member${batch.item_count === 1 ? '' : 's'}`}
              </strong>
              .
            </p>
            <p className="mt-2">
              {isRetry
                ? 'Members already paid will not be paid twice.'
                : `Total moving: ${formatMoney(batch.total_amount, batch.currency)}. Each member also gets an SMS advice once dispatched.`}
            </p>
          </>
        }
      />

      <ConfirmDialog
        open={dialog === 'cancel'}
        title="Cancel this run?"
        tone="danger"
        confirmLabel="Cancel run"
        busy={cancel.isPending}
        onClose={() => setDialog(null)}
        onConfirm={doCancel}
        description={
          <p>
            It will pay nobody. {batch.paid_count > 0 &&
              'Some payments were already recorded — cancelling does not reverse those.'}
            Create a new run when the balances are right.
          </p>
        }
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

type StepState = 'done' | 'current' | 'upcoming' | 'cancelled'

const STEP_ORDER: PayoutStatus[] = ['draft', 'approved', 'dispatched']

function StatusStepper({ status }: { status: PayoutStatus }) {
  const labels = ['Draft', 'Approved', 'Dispatched']
  const current = isRetryOrReached(status)
  return (
    <ol className="mb-5 flex flex-wrap items-center gap-x-2 gap-y-2 text-[13px] font-medium">
      {labels.map((label, index) => {
        const state: StepState =
          status === 'cancelled'
            ? index === 0
              ? 'done'
              : 'upcoming'
            : index < current
              ? 'done'
              : index === current
                ? 'current'
                : 'upcoming'
        return (
          <li key={label} className="flex items-center gap-2">
            {index > 0 && (
              <span
                aria-hidden="true"
                className={cn(
                  'h-px w-6 sm:w-10',
                  index <= current || status === 'cancelled'
                    ? 'bg-stone-300'
                    : 'bg-stone-200',
                )}
              />
            )}
            <StepNode label={label} state={state} marker={index + 1} />
          </li>
        )
      })}
      {status === 'cancelled' && (
        <>
          <span aria-hidden="true" className="h-px w-6 bg-stone-300 sm:w-10" />
          <StepNode label="Cancelled" state="cancelled" marker={0} />
        </>
      )}
    </ol>
  )
}

function isRetryOrReached(status: PayoutStatus): number {
  const i = STEP_ORDER.indexOf(status)
  return i === -1 ? 0 : i
}

function StepNode({
  label,
  state,
  marker,
}: {
  label: string
  state: StepState
  marker: number
}) {
  return (
    <span className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className={cn(
          'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold',
          state === 'done' && 'bg-primary-600 text-white',
          state === 'current' &&
            'border-2 border-primary-600 bg-primary-soft text-primary-ink',
          state === 'upcoming' && 'border border-stone-300 text-stone-400',
          state === 'cancelled' && 'bg-danger-soft text-danger-ink',
        )}
      >
        {state === 'done' ? (
          <Check className="h-3.5 w-3.5" />
        ) : state === 'cancelled' ? (
          <Ban className="h-3.5 w-3.5" />
        ) : (
          marker
        )}
      </span>
      <span
        className={cn(
          state === 'upcoming' && 'text-stone-400',
          state === 'cancelled' && 'text-danger-ink',
          (state === 'done' || state === 'current') && 'text-foreground',
        )}
      >
        {label}
      </span>
    </span>
  )
}

function RunProgress({ batch }: { batch: PayoutBatch }) {
  if (batch.item_count === 0) return null
  const paid = batch.paid_count
  const failed = batch.failed_count
  const pending = Math.max(0, batch.item_count - paid - failed)
  const pct = (n: number) => `${(n / batch.item_count) * 100}%`
  return (
    <div className="mb-5">
      <div
        role="img"
        aria-label={`${paid} of ${batch.item_count} members paid${
          failed > 0 ? `, ${failed} failed` : ''
        }`}
        className="flex h-2 overflow-hidden rounded-full bg-stone-100"
      >
        <div className="h-full bg-success transition-[width] duration-300" style={{ width: pct(paid) }} />
        <div className="h-full bg-danger transition-[width] duration-300" style={{ width: pct(failed) }} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground tabular-nums">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-success" />
          {paid} paid
        </span>
        {failed > 0 && (
          <span className="flex items-center gap-1.5 text-danger-ink">
            <span className="h-2 w-2 rounded-full bg-danger" />
            {failed} failed
          </span>
        )}
        {pending > 0 && batch.status !== 'cancelled' && (
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-stone-300" />
            {pending} pending
          </span>
        )}
      </div>
    </div>
  )
}
