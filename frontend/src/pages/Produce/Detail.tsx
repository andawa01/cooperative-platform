import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Power } from 'lucide-react'

import { ErrorState, Loading } from '@/components/common/Loading'
import { StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import {
  useCreateRate,
  useDeactivateProduceLine,
  useProduceLine,
  useRates,
} from '@/hooks/useProduceLines'
import { formatMoney } from '@/lib/auth'

export default function ProduceDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const line = useProduceLine(id)
  const rates = useRates(id)
  const createRate = useCreateRate(id!)
  const deactivate = useDeactivateProduceLine(id!)

  const [showRateForm, setShowRateForm] = useState(false)
  const [newRate, setNewRate] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState(
    new Date().toISOString().slice(0, 10),
  )
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  if (line.isLoading) return <Loading />
  if (line.error)
    return (
      <div className="p-6">
        <ErrorState
          message={(line.error as Error).message}
          onRetry={() => line.refetch()}
        />
      </div>
    )
  if (!line.data) return null

  const l = line.data
  const sortedRates = rates.data ?? []

  const submitRate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccessMessage(null)
    const value = Number(newRate)
    if (!Number.isFinite(value) || value <= 0) {
      setError('Rate must be a positive number.')
      return
    }
    try {
      const res = await createRate.mutateAsync({
        rate_per_unit: value.toFixed(4),
        currency: 'KES',
        effective_from: effectiveFrom,
      })
      const affected = res.affected_deliveries
      let msg = `Rate set. Previous rate closed.`
      if (affected > 0) {
        msg += ` ${affected} deliver${affected === 1 ? 'y' : 'ies'} recorded in the affected window may need review.`
      }
      setSuccessMessage(msg)
      setNewRate('')
      setShowRateForm(false)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const doDeactivate = async () => {
    if (
      !confirm(
        'Deactivate this produce line? Historical deliveries remain valid. New deliveries cannot be recorded against it.',
      )
    )
      return
    setError(null)
    try {
      await deactivate.mutateAsync()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="p-4 md:p-6">
      <Link
        to="/produce"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to produce
      </Link>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold text-gray-900">{l.name}</h1>
            <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-mono text-gray-600">
              {l.code}
            </span>
            {!l.is_active && <StatusBadge tone="neutral">Inactive</StatusBadge>}
          </div>
          <p className="mt-1 text-sm text-gray-600">
            per {l.unit}
            {l.description ? ` · ${l.description}` : ''}
          </p>
        </div>

        {isAdmin && l.is_active && (
          <button
            onClick={doDeactivate}
            disabled={deactivate.isPending}
            className="inline-flex items-center gap-2 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
          >
            <Power className="h-4 w-4" />
            {deactivate.isPending ? 'Deactivating…' : 'Deactivate'}
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {successMessage && (
        <div className="mb-4 rounded-md bg-green-50 p-3 text-sm text-green-800">
          {successMessage}
        </div>
      )}

      <section className="rounded-lg border border-gray-200 bg-white">
        <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Rate history
          </h2>
          {isAdmin && l.is_active && !showRateForm && (
            <button
              onClick={() => {
                setShowRateForm(true)
                setNewRate('')
                setError(null)
              }}
              className="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700"
            >
              Set new rate
            </button>
          )}
        </div>

        {showRateForm && (
          <form
            onSubmit={submitRate}
            className="border-b border-gray-200 bg-gray-50 px-5 py-4"
          >
            <p className="mb-3 text-xs text-gray-600">
              Setting a new rate closes the current one at the new effective
              date. Past deliveries keep their original snapshot.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Rate per {l.unit}
                </label>
                <input
                  type="number"
                  inputMode="decimal"
                  step="0.0001"
                  min="0"
                  required
                  value={newRate}
                  onChange={(e) => setNewRate(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  placeholder="0.00"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">
                  Effective from
                </label>
                <input
                  type="date"
                  required
                  value={effectiveFrom}
                  onChange={(e) => setEffectiveFrom(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="submit"
                disabled={createRate.isPending}
                className="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-60"
              >
                {createRate.isPending ? 'Saving…' : 'Save rate'}
              </button>
              <button
                type="button"
                onClick={() => setShowRateForm(false)}
                className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>
        )}

        {rates.isLoading && <Loading label="Loading rates…" />}
        {rates.error && (
          <div className="p-4">
            <ErrorState message={(rates.error as Error).message} />
          </div>
        )}
        {rates.data && rates.data.length === 0 && (
          <p className="px-5 py-6 text-sm text-gray-500">
            No rate has ever been set for this line. Deliveries will be
            recorded without a value until a rate exists.
          </p>
        )}
        {rates.data && rates.data.length > 0 && (
          <ul className="divide-y divide-gray-100">
            {sortedRates.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-4 px-5 py-3 text-sm"
              >
                <div>
                  <div className="font-medium text-gray-900">
                    {formatMoney(r.rate_per_unit, r.currency)} per {l.unit}
                  </div>
                  <div className="text-xs text-gray-500">
                    from {r.effective_from}
                    {r.effective_to
                      ? ` to ${r.effective_to}`
                      : ' · current'}
                  </div>
                </div>
                {!r.effective_to && <StatusBadge tone="success">Current</StatusBadge>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}