import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, RotateCcw } from 'lucide-react'

import { ErrorState, Loading } from '@/components/common/Loading'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import { usePayment, useReversePayment } from '@/hooks/usePayments'
import { useFarmer } from '@/hooks/useFarmers'
import { formatMoney } from '@/lib/auth'

export default function PaymentDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const payment = usePayment(id)
  const farmer = useFarmer(payment.data?.farmer_id)
  const reverse = useReversePayment(id!)
  const [actionError, setActionError] = useState<string | null>(null)

  if (payment.isLoading) return <Loading />
  if (payment.error)
    return (
      <div className="p-6">
        <ErrorState
          message={(payment.error as Error).message}
          onRetry={() => payment.refetch()}
        />
      </div>
    )
  if (!payment.data) return null

  const p = payment.data
  const isReversal = p.reversal_of_id !== null
  const unallocated = Number(p.unallocated_amount)

  const doReverse = async () => {
    setActionError(null)
    const reason = prompt(
      'Reason for reversing this payment (this action is auditable):',
    )
    if (!reason || reason.trim().length === 0) return
    try {
      await reverse.mutateAsync({ reason: reason.trim() })
      navigate('/payments')
    } catch (err) {
      setActionError((err as Error).message)
    }
  }

  return (
    <div className="p-4 md:p-6">
      <Link
        to="/payments"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to payments
      </Link>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-gray-900">
              {formatMoney(p.amount, p.currency)}
            </h1>
            {isReversal && (
              <StatusBadge tone="danger">
                <RotateCcw className="mr-1 h-3 w-3" />
                Reversal
              </StatusBadge>
            )}
            {unallocated > 0 && !isReversal && (
              <StatusBadge tone="info">
                {formatMoney(unallocated, p.currency)} unallocated
              </StatusBadge>
            )}
          </div>
          <p className="mt-1 text-sm text-gray-600">
            {farmer.data
              ? `${farmer.data.first_name} ${farmer.data.last_name}`
              : 'Loading…'}{' '}
            · {new Date(p.paid_at).toLocaleString()}
          </p>
        </div>

        {isAdmin && !isReversal && (
          <button
            onClick={doReverse}
            disabled={reverse.isPending}
            className="inline-flex items-center gap-2 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
          >
            <RotateCcw className="h-4 w-4" />
            {reverse.isPending ? 'Reversing…' : 'Reverse'}
          </button>
        )}
      </div>

      {actionError && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Payment
          </h2>
          <dl className="space-y-3 text-sm">
            <Row label="Amount" value={formatMoney(p.amount, p.currency)} />
            <Row label="Method" value={p.method.replace('_', ' ')} />
            {p.reference && <Row label="Reference" value={p.reference} />}
            <Row label="Paid at" value={new Date(p.paid_at).toLocaleString()} />
            <Row label="Recorded at" value={new Date(p.recorded_at).toLocaleString()} />
            <Row
              label="Unallocated"
              value={formatMoney(p.unallocated_amount, p.currency)}
            />
            {p.notes && <Row label="Notes" value={p.notes} />}
            {p.reversal_of_id && (
              <Row label="Reverses" value={p.reversal_of_id} mono />
            )}
          </dl>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Allocations ({p.allocations.length})
          </h2>
          {p.allocations.length === 0 ? (
            <p className="text-sm text-gray-500">
              No deliveries were allocated against this payment. The full amount
              is credit on account.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {p.allocations.map((a) => (
                <li
                  key={a.id}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <Link
                    to={`/deliveries/${a.delivery_id}`}
                    className="truncate text-primary-700 hover:text-primary-800"
                  >
                    Delivery {a.delivery_id.slice(0, 8)}…
                  </Link>
                  <span
                    className={
                      Number(a.amount) < 0 ? 'text-red-700' : 'text-gray-900'
                    }
                  >
                    {formatMoney(a.amount, p.currency)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

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