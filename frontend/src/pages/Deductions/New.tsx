import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Info, Loader2, MinusCircle } from 'lucide-react'

import { FarmerPicker } from '@/components/common/FarmerPicker'
import { Button } from '@/components/common/Button'
import { Card, CardBody, CardFooter } from '@/components/common/Card'
import {
  Field,
  FieldGroup,
  FormError,
  Select,
  TextArea,
  TextInput,
} from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'
import { ApiError } from '@/lib/api'
import { useCreateDeduction } from '@/hooks/useDeductions'
import { useFarmer, useFarmerBalance } from '@/hooks/useFarmers'
import { formatMoney } from '@/lib/auth'
import { toIsoDate } from '@/lib/datetime'
import {
  DEDUCTION_REASONS,
  DEDUCTION_REASON_HINTS,
  DEDUCTION_REASON_LABELS,
} from '@/lib/deductions'
import { cn } from '@/lib/utils'
import type { DeductionReason, Farmer } from '@/types/api'

export default function NewDeduction() {
  const [params] = useSearchParams()
  const farmerIdFromQuery = params.get('farmer_id')
  const navigate = useNavigate()
  const create = useCreateDeduction()

  const preselectedFarmer = useFarmer(farmerIdFromQuery ?? undefined)

  const [farmer, setFarmer] = useState<Farmer | null>(null)
  const [reason, setReason] = useState<DeductionReason>('transport')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('KES')
  const [reference, setReference] = useState('')
  const [appliedAt, setAppliedAt] = useState(toIsoDate())
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (preselectedFarmer.data) setFarmer(preselectedFarmer.data)
  }, [preselectedFarmer.data])

  const balance = useFarmerBalance(farmer?.id)

  /**
   * What the member's payable becomes if this is recorded. The clerk is about
   * to hand over money, so the consequence of the charge is shown before it is
   * committed rather than discovered afterwards.
   */
  const projected = useMemo(() => {
    if (!balance.data) return null
    const n = Number(amount)
    if (!Number.isFinite(n) || n <= 0) return null
    return Number(balance.data.net_payable) - n
  }, [balance.data, amount])

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!farmer) return setError('Please select a farmer.')
    const n = Number(amount)
    if (!Number.isFinite(n) || n <= 0) return setError('Amount must be positive.')

    try {
      const deduction = await create.mutateAsync({
        farmer_id: farmer.id,
        amount: n.toFixed(4),
        currency,
        reason_code: reason,
        reference: reference.trim() || null,
        // A charge belongs to a calendar day (the delivery or instalment
        // date), so the date input becomes local midnight, not UTC midnight.
        applied_at: new Date(`${appliedAt}T00:00:00`).toISOString(),
        notes: notes.trim() || null,
      })
      navigate(`/deductions/${deduction.id}`, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    }
  }

  return (
    <div>
      <PageHeader
        title="Record deduction"
        back={{ to: '/deductions', label: 'Deductions' }}
        description="Money withheld from a member's proceeds — transport, cess, input credit, a loan instalment. It reduces what they are paid; it does not change what they earned."
      />

      <form onSubmit={onSubmit} className="max-w-2xl">
        <Card>
          <CardBody className="space-y-6 p-5 sm:p-6">
            <FarmerPicker value={farmer} onChange={setFarmer} required />

            {farmer && balance.data && (
              <div className="rounded-lg border border-info/20 bg-info-soft p-3.5">
                <div className="flex items-start gap-2.5">
                  <Info className="mt-0.5 h-4 w-4 shrink-0 text-info-ink" />
                  <div className="space-y-1 text-sm text-info-ink">
                    <div className="flex flex-wrap items-baseline gap-x-1.5">
                      <span className="text-info-ink/80">Net payable today:</span>
                      <span className="font-semibold tabular-nums">
                        {formatMoney(balance.data.net_payable, balance.data.currency)}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-baseline gap-x-1.5 text-xs text-info-ink/80">
                      <span>Already withheld:</span>
                      <span className="font-medium tabular-nums">
                        {formatMoney(
                          balance.data.deductions_total,
                          balance.data.currency,
                        )}
                      </span>
                    </div>
                    {projected !== null && (
                      <div className="flex flex-wrap items-baseline gap-x-1.5 text-xs text-info-ink/80">
                        <span>After this deduction:</span>
                        <span
                          className={cn(
                            'font-semibold tabular-nums',
                            projected < 0 ? 'text-danger-ink' : 'text-info-ink',
                          )}
                        >
                          {formatMoney(projected, balance.data.currency)}
                        </span>
                        {projected < 0 && <span>(member owes the co-op)</span>}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
              <Field label="Amount withheld" htmlFor="amount" required>
                <input
                  id="amount"
                  type="number"
                  inputMode="decimal"
                  step="0.0001"
                  min="0"
                  required
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.00"
                  className="h-14 w-full rounded-lg border border-input bg-card px-3 text-2xl font-semibold tracking-tight text-foreground shadow-xs tabular-nums transition-[border-color,box-shadow] placeholder:font-normal placeholder:text-stone-300 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
                />
              </Field>
              <Field label="Currency" htmlFor="currency">
                <Select
                  id="currency"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="h-14"
                >
                  <option value="KES">KES</option>
                  <option value="UGX">UGX</option>
                  <option value="TZS">TZS</option>
                </Select>
              </Field>
            </div>

            <FieldGroup
              title="Reason"
              description={DEDUCTION_REASON_HINTS[reason]}
            >
              <Field label="Reason code" htmlFor="reason" required>
                <Select
                  id="reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value as DeductionReason)}
                >
                  {DEDUCTION_REASONS.map((r) => (
                    <option key={r} value={r}>
                      {DEDUCTION_REASON_LABELS[r]}
                    </option>
                  ))}
                </Select>
              </Field>
            </FieldGroup>

            <div className="border-t border-border/60 pt-5">
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    label="Applied on"
                    htmlFor="applied_at"
                    hint="The day the charge belongs to."
                    required
                  >
                    <TextInput
                      id="applied_at"
                      type="date"
                      required
                      value={appliedAt}
                      max={toIsoDate()}
                      onChange={(e) => setAppliedAt(e.target.value)}
                    />
                  </Field>

                  <Field
                    label="Reference"
                    htmlFor="reference"
                    hint="County receipt, loan account, input note."
                  >
                    <TextInput
                      id="reference"
                      value={reference}
                      onChange={(e) => setReference(e.target.value)}
                      placeholder="e.g. CESS-2026-118"
                    />
                  </Field>
                </div>

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
              to="/deductions"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </Link>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <MinusCircle className="h-4 w-4" />
              )}
              {create.isPending ? 'Recording…' : 'Record deduction'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}
