import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, RefreshCw, Sparkles } from 'lucide-react'

import { Button } from '@/components/common/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailRow,
} from '@/components/common/Card'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import {
  useDelivery,
  useReverseDelivery,
  useValueDelivery,
} from '@/hooks/useDeliveries'
import { useFarmer } from '@/hooks/useFarmers'
import { useProduceLine } from '@/hooks/useProduceLines'
import { formatMoney } from '@/lib/auth'

export default function DeliveryDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const delivery = useDelivery(id)
  const farmer = useFarmer(delivery.data?.farmer_id)
  const line = useProduceLine(delivery.data?.produce_line_id)
  const value = useValueDelivery(id!)
  const reverse = useReverseDelivery(id!)
  const [actionError, setActionError] = useState<string | null>(null)

  if (delivery.isLoading) return <Loading />
  if (delivery.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(delivery.error as Error).message}
          onRetry={() => delivery.refetch()}
        />
      </div>
    )
  if (!delivery.data) return null

  const d = delivery.data
  const isReversal = d.reversal_of_id !== null
  const isUnvalued = d.rate_snapshot === null

  const doValue = async () => {
    setActionError(null)
    try {
      await value.mutateAsync()
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  const doReverse = async () => {
    setActionError(null)
    const reason = prompt(
      'Reason for reversing this delivery (this action is auditable):',
    )
    if (!reason || reason.trim().length === 0) return
    try {
      await reverse.mutateAsync({ reason: reason.trim() })
      navigate('/deliveries')
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  return (
    <div>
      <PageHeader
        back={{ to: '/deliveries', label: 'Deliveries' }}
        title={
          farmer.data
            ? `${farmer.data.first_name} ${farmer.data.last_name}`
            : 'Delivery'
        }
        badge={
          <>
            {isReversal && <StatusBadge tone="danger">Reversal</StatusBadge>}
            {isUnvalued && !isReversal && (
              <StatusBadge tone="warning">Pending valuation</StatusBadge>
            )}
            {!isUnvalued && !isReversal && (
              <StatusBadge tone="success">Valued</StatusBadge>
            )}
          </>
        }
        description={
          <>
            {line.data?.name ?? 'Loading…'} ·{' '}
            {new Date(d.delivered_at).toLocaleString()}
          </>
        }
        action={
          <>
            {isAdmin && isUnvalued && !isReversal && (
              <Button
                variant="primary"
                onClick={doValue}
                disabled={value.isPending}
              >
                <Sparkles className="h-4 w-4" />
                {value.isPending ? 'Valuing…' : 'Value now'}
              </Button>
            )}
            {isAdmin && !isReversal && (
              <Button
                variant="danger"
                onClick={doReverse}
                disabled={reverse.isPending}
              >
                <RefreshCw className="h-4 w-4" />
                {reverse.isPending ? 'Reversing…' : 'Reverse'}
              </Button>
            )}
          </>
        }
      />

      {actionError && (
        <div className="mb-4 rounded-lg border border-danger/20 bg-danger-soft px-3 py-2.5 text-sm text-danger-ink">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        {/* The value is the headline */}
        <Card className="lg:col-span-2">
          <CardHeader title="Valuation" />
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="rounded-xl border border-border bg-stone-50 p-4">
                <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                  Quantity
                </div>
                <div className="mt-1.5 text-[26px] leading-none font-semibold text-foreground tabular-nums">
                  {Number(d.quantity).toLocaleString(undefined, {
                    maximumFractionDigits: 4,
                  })}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">
                    {line.data?.unit ?? ''}
                  </span>
                </div>
              </div>

              <div
                className={
                  d.amount
                    ? 'rounded-xl border border-primary-100 bg-primary-soft/60 p-4'
                    : 'rounded-xl border border-warning/25 bg-warning-soft p-4'
                }
              >
                <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
                  Amount
                </div>
                <div className="mt-1.5 text-[26px] leading-none font-semibold text-foreground tabular-nums">
                  {d.amount
                    ? formatMoney(d.amount, d.currency_snapshot)
                    : 'Not valued'}
                </div>
              </div>
            </div>

            <dl className="mt-5 space-y-3 border-t border-border/60 pt-4">
              <DetailRow
                label="Rate applied"
                value={
                  d.rate_snapshot
                    ? `${d.rate_snapshot} ${d.currency_snapshot}`
                    : 'Pending'
                }
              />
              <DetailRow
                label="Delivered at"
                value={new Date(d.delivered_at).toLocaleString()}
              />
              <DetailRow
                label="Recorded at"
                value={new Date(d.recorded_at).toLocaleString()}
              />
              {d.location && <DetailRow label="Location" value={d.location} />}
              {d.notes && <DetailRow label="Notes" value={d.notes} />}
              {d.reversal_of_id && (
                <DetailRow label="Reverses" value={d.reversal_of_id} mono />
              )}
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Farmer" />
          <CardBody>
            {farmer.data ? (
              <Link
                to={`/farmers/${farmer.data.id}`}
                className="group flex items-center justify-between gap-3 rounded-lg border border-border/80 p-3 transition-colors hover:border-primary-300 hover:bg-primary-soft/40"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-foreground">
                    {farmer.data.first_name} {farmer.data.last_name}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground tabular-nums">
                    {farmer.data.phone}
                  </span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 text-stone-400 transition-transform group-hover:translate-x-0.5 group-hover:text-primary-ink" />
              </Link>
            ) : (
              <p className="text-sm text-muted-foreground">Loading farmer…</p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
