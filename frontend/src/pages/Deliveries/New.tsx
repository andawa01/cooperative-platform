import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Check, Loader2, Package } from 'lucide-react'

import { FarmerPicker } from '@/components/common/FarmerPicker'
import { Button } from '@/components/common/Button'
import { Card, CardBody, CardFooter } from '@/components/common/Card'
import {
  Field,
  FormError,
  TextArea,
  TextInput,
} from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'
import { ApiError } from '@/lib/api'
import { useCreateDelivery } from '@/hooks/useDeliveries'
import { useFarmer } from '@/hooks/useFarmers'
import { useProduceLines } from '@/hooks/useProduceLines'
import { cn } from '@/lib/utils'
import type { Farmer } from '@/types/api'

export default function NewDelivery() {
  const [params] = useSearchParams()
  const farmerIdFromQuery = params.get('farmer_id')
  const navigate = useNavigate()
  const create = useCreateDelivery()

  const preselectedFarmer = useFarmer(farmerIdFromQuery ?? undefined)

  const [farmer, setFarmer] = useState<Farmer | null>(null)
  const [produceLineId, setProduceLineId] = useState<string>('')
  const [quantity, setQuantity] = useState<string>('')
  const [location, setLocation] = useState<string>('')
  const [notes, setNotes] = useState<string>('')
  const [error, setError] = useState<string | null>(null)

  // Hydrate the farmer if the query string gave us one.
  useEffect(() => {
    if (preselectedFarmer.data) setFarmer(preselectedFarmer.data)
  }, [preselectedFarmer.data])

  const produceLines = useProduceLines({ include_inactive: false, limit: 100 })
  const activeLines = produceLines.data?.items ?? []

  // Pick a default produce line on first load if there's only one.
  useEffect(() => {
    if (!produceLineId && activeLines.length > 0) {
      setProduceLineId(activeLines[0].id)
    }
  }, [produceLineId, activeLines])

  const selectedLine = activeLines.find((l) => l.id === produceLineId)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!farmer) return setError('Please select a farmer.')
    if (!produceLineId) return setError('Please select a produce line.')
    const q = Number(quantity)
    if (!Number.isFinite(q) || q <= 0)
      return setError('Quantity must be a positive number.')

    try {
      const delivery = await create.mutateAsync({
        farmer_id: farmer.id,
        produce_line_id: produceLineId,
        quantity: q.toFixed(4),
        delivered_at: new Date().toISOString(),
        location: location.trim() || null,
        notes: notes.trim() || null,
      })
      navigate(`/deliveries/${delivery.id}`, { replace: true })
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
      } else {
        setError('Something went wrong.')
      }
    }
  }

  return (
    <div>
      <PageHeader
        title="Record delivery"
        back={{ to: '/deliveries', label: 'Deliveries' }}
        description="Use the moment the produce was physically received — the rate is snapshotted from that date."
      />

      <form onSubmit={onSubmit} className="max-w-2xl">
        <Card>
          <CardBody className="space-y-6 p-5 sm:p-6">
            <FarmerPicker value={farmer} onChange={setFarmer} required />

            <div>
              <span className="flex items-center gap-1 text-sm font-medium text-stone-700">
                Produce line
                <span className="text-danger" aria-hidden="true">
                  *
                </span>
              </span>
              {produceLines.isLoading && (
                <p className="mt-2 text-sm text-muted-foreground">
                  Loading produce lines…
                </p>
              )}
              {produceLines.error && (
                <p className="mt-2 text-sm text-danger-ink">
                  Failed to load produce lines.
                </p>
              )}
              {produceLines.data && (
                <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {activeLines.map((l) => {
                    const selected = produceLineId === l.id
                    return (
                      <button
                        key={l.id}
                        type="button"
                        onClick={() => setProduceLineId(l.id)}
                        className={cn(
                          'relative flex flex-col items-start gap-0.5 rounded-lg border px-3 py-3 text-left transition-colors',
                          selected
                            ? 'border-primary-500 bg-primary-soft/70 text-primary-ink ring-1 ring-primary-500/20'
                            : 'border-border bg-card text-stone-700 hover:border-primary-300 hover:bg-primary-soft/30',
                        )}
                      >
                        <span className="text-sm font-medium">{l.name}</span>
                        <span className="text-xs text-muted-foreground">
                          per {l.unit}
                        </span>
                        {selected && (
                          <span className="absolute top-2 right-2 flex h-4 w-4 items-center justify-center rounded-full bg-primary-600 text-white">
                            <Check className="h-2.5 w-2.5" />
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>

            <Field
              label={`Quantity${selectedLine ? ` (${selectedLine.unit})` : ''}`}
              htmlFor="quantity"
              required
              hint="Four decimal places are stored; the ledger never rounds mid-calculation."
            >
              <input
                id="quantity"
                type="number"
                inputMode="decimal"
                step="0.0001"
                min="0"
                required
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="0"
                className="h-14 w-full rounded-lg border border-input bg-card px-3 text-2xl font-semibold tracking-tight text-foreground shadow-xs tabular-nums transition-[border-color,box-shadow] placeholder:font-normal placeholder:text-stone-300 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
              />
            </Field>

            <div className="border-t border-border/60 pt-5">
              <div className="space-y-4">
                <Field
                  label="Collection point / location"
                  htmlFor="location"
                  hint="Optional — where the produce was handed over."
                >
                  <TextInput
                    id="location"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder="e.g. Kisumu Central shed"
                  />
                </Field>

                <Field label="Notes" htmlFor="notes">
                  <TextArea
                    id="notes"
                    rows={2}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </Field>
              </div>
            </div>

            {error && <FormError>{error}</FormError>}
          </CardBody>

          <CardFooter className="justify-end">
            <Link
              to="/deliveries"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </Link>
            <Button
              type="submit"
              variant="primary"
              disabled={create.isPending}
            >
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Package className="h-4 w-4" />
              )}
              {create.isPending ? 'Recording…' : 'Record delivery'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}
