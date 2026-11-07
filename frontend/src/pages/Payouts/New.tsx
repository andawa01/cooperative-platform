import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { HandCoins, Info, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/common/Button'
import { Card, CardBody, CardFooter } from '@/components/common/Card'
import { Field, FormError, TextArea } from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'
import { ApiError } from '@/lib/api'
import { useCreatePayoutRun } from '@/hooks/usePayouts'
import type { PaymentMethod } from '@/types/api'

const METHODS: { value: PaymentMethod; label: string; hint: string }[] = [
  {
    value: 'mobile_money',
    label: 'Mobile money',
    hint: 'M-Pesa B2C — the export lists phone numbers',
  },
  {
    value: 'bank_transfer',
    label: 'Bank transfer',
    hint: 'Export and upload to the bank',
  },
  { value: 'cash', label: 'Cash', hint: 'Paid over the counter against the list' },
]

export default function NewPayoutRun() {
  const navigate = useNavigate()
  const create = useCreatePayoutRun()
  const [method, setMethod] = useState<PaymentMethod>('mobile_money')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      const run = await create.mutateAsync({
        method,
        notes: notes.trim() || null,
      })
      navigate(`/payouts/${run.id}`, { replace: true })
      toast.success('Draft run created', {
        description: `${run.item_count} member${run.item_count === 1 ? '' : 's'} included. Nothing is paid until an admin approves and dispatches it.`,
      })
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'The run could not be created.',
      )
    }
  }

  return (
    <div>
      <PageHeader
        title="New payout run"
        back={{ to: '/payouts', label: 'Payout runs' }}
        description="Every member with a positive payable is included at the amount they are owed today. Nothing is paid until an admin approves the run and dispatches it."
      />

      <form onSubmit={onSubmit} className="max-w-2xl">
        <Card>
          <CardBody className="space-y-6 p-5 sm:p-6">
            <div className="rounded-lg border border-info/20 bg-info-soft p-3.5">
              <div className="flex items-start gap-2.5">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-info-ink" />
                <div className="space-y-1 text-sm text-info-ink">
                  <p className="font-medium">Amounts are frozen when the run is created.</p>
                  <p className="text-xs text-info-ink/80">
                    A delivery or deduction recorded afterwards changes the
                    member&apos;s balance, not this run. Re-run when the numbers
                    settle down.
                  </p>
                </div>
              </div>
            </div>

            <p className="text-xs text-muted-foreground">
              The run includes all active members with a positive payable. To
              exclude someone, adjust their balance first — per-member selection
              is not on this screen yet.
            </p>

            <div>
              <span className="flex items-center gap-1 text-sm font-medium text-stone-700">
                Payout rail
                <span className="text-danger" aria-hidden="true">
                  *
                </span>
              </span>
              <div className="mt-1.5 space-y-2">
                {METHODS.map((option) => {
                  const selected = method === option.value
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setMethod(option.value)}
                      aria-pressed={selected}
                      className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                        selected
                          ? 'border-primary-500 bg-primary-soft/70 ring-1 ring-primary-500/20'
                          : 'border-border bg-card hover:border-primary-300 hover:bg-primary-soft/30'
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block text-sm font-medium text-foreground">
                          {option.label}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          {option.hint}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            <Field label="Notes" htmlFor="notes">
              <TextArea
                id="notes"
                rows={2}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. October cherry settlement, second payment"
              />
            </Field>

            {error && <FormError>{error}</FormError>}
          </CardBody>

          <CardFooter className="justify-end">
            <Link
              to="/payouts"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </Link>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <HandCoins className="h-4 w-4" />
              )}
              {create.isPending ? 'Preparing…' : 'Create draft run'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}