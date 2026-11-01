import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Loader2, Power, TrendingUp } from 'lucide-react'

import { Button } from '@/components/common/Button'
import { Card, CardBody, CardHeader } from '@/components/common/Card'
import {
  Field,
  FormError,
  TextInput,
} from '@/components/common/Form'
import { ErrorState, Loading } from '@/components/common/Loading'
import { PageHeader } from '@/components/common/PageHeader'
import { Chip, StatusBadge } from '@/components/common/StatusBadge'
import { useAuth } from '@/hooks/useAuth'
import {
  useCreateRate,
  useDeactivateProduceLine,
  useProduceLine,
  useRates,
} from '@/hooks/useProduceLines'
import { formatMoney } from '@/lib/auth'
import { formatDate, toIsoDate } from '@/lib/datetime'

export default function ProduceDetail() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const line = useProduceLine(id)
  const rates = useRates(id)
  const createRate = useCreateRate(id!)
  const deactivate = useDeactivateProduceLine(id!)

  const [showRateForm, setShowRateForm] = useState(false)
  const [newRate, setNewRate] = useState('')
  const [effectiveFrom, setEffectiveFrom] = useState(toIsoDate())
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  if (line.isLoading) return <Loading />
  if (line.error)
    return (
      <div className="py-6">
        <ErrorState
          message={(line.error as Error).message}
          onRetry={() => line.refetch()}
        />
      </div>
    )
  if (!line.data) return null

  const l = line.data
  const sortedRates = rates.data ?? []
  const currentRate = sortedRates.find((r) => !r.effective_to)

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
    <div>
      <PageHeader
        back={{ to: '/produce', label: 'Produce & Rates' }}
        title={l.name}
        badge={
          <>
            <Chip>{l.code}</Chip>
            {!l.is_active && <StatusBadge tone="neutral">Inactive</StatusBadge>}
          </>
        }
        description={
          <>
            Priced per {l.unit}
            {l.description ? ` · ${l.description}` : ''}
          </>
        }
        action={
          isAdmin &&
          l.is_active && (
            <Button
              variant="danger"
              onClick={doDeactivate}
              disabled={deactivate.isPending}
            >
              <Power className="h-4 w-4" />
              {deactivate.isPending ? 'Deactivating…' : 'Deactivate'}
            </Button>
          )
        }
      />

      {/* Current rate */}
      <div className="mb-4 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardBody className="p-5">
            <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
              Current rate
            </div>
            <div className="mt-1.5 text-[28px] leading-none font-semibold text-foreground tabular-nums">
              {currentRate
                ? formatMoney(currentRate.rate_per_unit, currentRate.currency)
                : '—'}
              {currentRate && (
                <span className="ml-1 text-sm font-normal text-muted-foreground">
                  / {l.unit}
                </span>
              )}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              {currentRate
                ? `Effective since ${formatDate(currentRate.effective_from)}`
                : 'No rate set — deliveries will be recorded unvalued.'}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardBody className="p-5">
            <div className="text-[11px] font-semibold tracking-wider text-stone-500 uppercase">
              Rate changes
            </div>
            <div className="mt-1.5 text-[28px] leading-none font-semibold text-foreground tabular-nums">
              {sortedRates.length}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">
              Append-only history — past deliveries keep their snapshot.
            </div>
          </CardBody>
        </Card>
      </div>

      {error && (
        <div className="mb-4">
          <FormError>{error}</FormError>
        </div>
      )}
      {successMessage && (
        <div className="mb-4 rounded-lg border border-success/25 bg-success-soft px-3 py-2.5 text-sm text-success-ink">
          {successMessage}
        </div>
      )}

      <Card>
        <CardHeader
          title="Rate history"
          divider={showRateForm}
          action={
            isAdmin &&
            l.is_active &&
            !showRateForm && (
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setShowRateForm(true)
                  setNewRate('')
                  setError(null)
                }}
              >
                <TrendingUp className="h-3.5 w-3.5" />
                Set new rate
              </Button>
            )
          }
        />

        {showRateForm && (
          <form
            onSubmit={submitRate}
            className="animate-in fade-in border-b border-border/70 bg-stone-50/60 px-5 py-4 duration-200"
          >
            <p className="mb-3 text-xs text-muted-foreground">
              Setting a new rate closes the current one at the new effective
              date. Past deliveries keep their original snapshot.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={`Rate per ${l.unit}`} htmlFor="new-rate" required>
                <TextInput
                  id="new-rate"
                  type="number"
                  inputMode="decimal"
                  step="0.0001"
                  min="0"
                  required
                  value={newRate}
                  onChange={(e) => setNewRate(e.target.value)}
                  placeholder="0.00"
                />
              </Field>
              <Field label="Effective from" htmlFor="effective-from" required>
                <TextInput
                  id="effective-from"
                  type="date"
                  required
                  value={effectiveFrom}
                  onChange={(e) => setEffectiveFrom(e.target.value)}
                />
              </Field>
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                type="submit"
                variant="primary"
                size="sm"
                disabled={createRate.isPending}
              >
                {createRate.isPending && (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                )}
                {createRate.isPending ? 'Saving…' : 'Save rate'}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowRateForm(false)}
              >
                Cancel
              </Button>
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
          <p className="px-5 py-10 text-center text-sm text-muted-foreground">
            No rate has ever been set for this line. Deliveries will be recorded
            without a value until a rate exists.
          </p>
        )}
        {rates.data && rates.data.length > 0 && (
          <ul className="divide-y divide-border/60">
            {sortedRates.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-4 px-5 py-3.5"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-foreground tabular-nums">
                    {formatMoney(r.rate_per_unit, r.currency)} per {l.unit}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground tabular-nums">
                    from {formatDate(r.effective_from)}
                    {r.effective_to
                      ? ` to ${formatDate(r.effective_to)}`
                      : ' · current'}
                  </div>
                </div>
                {!r.effective_to ? (
                  <StatusBadge tone="success">Current</StatusBadge>
                ) : (
                  <StatusBadge tone="neutral" dot={false}>
                    Closed
                  </StatusBadge>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}
