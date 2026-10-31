import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Sparkles } from 'lucide-react'

import { ErrorState, Loading } from '@/components/common/Loading'
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
      <div className="p-6">
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
    <div className="p-4 md:p-6">
      <Link
        to="/deliveries"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to deliveries
      </Link>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-gray-900">
              {farmer.data
                ? `${farmer.data.first_name} ${farmer.data.last_name}`
                : 'Delivery'}
            </h1>
            {isReversal && <StatusBadge tone="danger">Reversal</StatusBadge>}
            {isUnvalued && <StatusBadge tone="warning">Pending valuation</StatusBadge>}
          </div>
          <p className="mt-1 text-sm text-gray-600">
            {line.data?.name ?? 'Loading…'} — {new Date(d.delivered_at).toLocaleString()}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {isAdmin && isUnvalued && !isReversal && (
            <button
              onClick={doValue}
              disabled={value.isPending}
              className="inline-flex items-center gap-2 rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
            >
              <Sparkles className="h-4 w-4" />
              {value.isPending ? 'Valuing…' : 'Value now'}
            </button>
          )}
          {isAdmin && !isReversal && (
            <button
              onClick={doReverse}
              disabled={reverse.isPending}
              className="inline-flex items-center gap-2 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
            >
              <RefreshCw className="h-4 w-4" />
              {reverse.isPending ? 'Reversing…' : 'Reverse'}
            </button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Details
        </h2>
        <dl className="space-y-3 text-sm">
          <Row label="Quantity" value={`${d.quantity} ${line.data?.unit ?? ''}`} />
          <Row
            label="Rate applied"
            value={d.rate_snapshot ? `${d.rate_snapshot} ${d.currency_snapshot}` : 'Pending'}
          />
          <Row
            label="Amount"
            value={d.amount ? formatMoney(d.amount, d.currency_snapshot) : '—'}
          />
          <Row
            label="Delivered at"
            value={new Date(d.delivered_at).toLocaleString()}
          />
          <Row label="Recorded at" value={new Date(d.recorded_at).toLocaleString()} />
          {d.location && <Row label="Location" value={d.location} />}
          {d.notes && <Row label="Notes" value={d.notes} />}
          {d.reversal_of_id && (
            <Row label="Reverses" value={d.reversal_of_id} mono />
          )}
        </dl>
      </section>

      {farmer.data && (
        <div className="mt-6">
          <Link
            to={`/farmers/${farmer.data.id}`}
            className="text-sm text-primary-700 hover:text-primary-800"
          >
            View farmer profile →
          </Link>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-gray-600">{label}</dt>
      <dd className={`text-right text-gray-900 ${mono ? 'font-mono text-xs' : ''}`}>
        {value}
      </dd>
    </div>
  )
}