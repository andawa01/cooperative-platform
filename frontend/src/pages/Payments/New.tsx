import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Banknote, Info, Loader2 } from 'lucide-react'

import { FarmerPicker } from '@/components/common/FarmerPicker'
import { Button } from '@/components/common/Button'
import { Card, CardBody, CardFooter } from '@/components/common/Card'
import {
  Field,
  FormError,
  Select,
  TextArea,
  TextInput,
} from '@/components/common/Form'
import { PageHeader } from '@/components/common/PageHeader'
import { ApiError } from '@/lib/api'
import { useCreatePayment } from '@/hooks/usePayments'
import { useFarmer, useFarmerBalance } from '@/hooks/useFarmers'
import { cn } from '@/lib/utils'
import { formatMoney } from '@/lib/auth'
import type { Farmer, PaymentMethod } from '@/types/api'

const METHODS: { value: PaymentMethod; label: string }[] = [
  { value: 'cash', label: 'Cash' },
  { value: 'mobile_money', label: 'Mobile money' },
  { value: 'bank_transfer', label: 'Bank transfer' },
]

export default function NewPayment() {
  const [params] = useSearchParams()
  const farmerIdFromQuery = params.get('farmer_id')
  const navigate = useNavigate()
  const create = useCreatePayment()

  const preselectedFarmer = useFarmer(farmerIdFromQuery ?? undefined)

  const [farmer, setFarmer] = useState<Farmer | null>(null)
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('KES')
  const [method, setMethod] = useState<PaymentMethod>('mobile_money')
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Fresh UUID per form mount. Retries of the same submission reuse it.
  const idempotencyKey = useMemo(() => `web-${crypto.randomUUID()}`, [])

  useEffect(() => {
    if (preselectedFarmer.data) setFarmer(preselectedFarmer.data)
  }, [preselectedFarmer.data])

  const balance = useFarmerBalance(farmer?.id)

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!farmer) return setError('Please select a farmer.')
    const n = Number(amount)
    if (!Number.isFinite(n) || n <= 0) return setError('Amount must be positive.')

    try {
      const payment = await create.mutateAsync({
        farmer_id: farmer.id,
        amount: n.toFixed(4),
        currency,
        method,
        reference: reference.trim() || null,
        paid_at: new Date().toISOString(),
        idempotency_key: idempotencyKey,
        notes: notes.trim() || null,
        // No `allocations` field: server allocates FIFO.
      })
      navigate(`/payments/${payment.id}`, { replace: true })
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
        title="Record payment"
        back={{ to: '/payments', label: 'Payments' }}
        description="The system allocates this against the farmer's oldest unpaid deliveries (FIFO). Any excess becomes credit on account."
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
                      <span className="text-info-ink/80">Outstanding debt:</span>
                      <span className="font-semibold tabular-nums">
                        {formatMoney(
                          balance.data.outstanding_debt,
                          balance.data.currency,
                        )}
                      </span>
                    </div>
                    {Number(balance.data.available_credit) > 0 && (
                      <div className="flex flex-wrap items-baseline gap-x-1.5">
                        <span className="text-info-ink/80">Available credit:</span>
                        <span className="font-semibold tabular-nums">
                          {formatMoney(
                            balance.data.available_credit,
                            balance.data.currency,
                          )}
                        </span>
                      </div>
                    )}
                    {balance.data.pending_valuation_deliveries > 0 && (
                      <div className="text-xs text-info-ink/80">
                        {balance.data.pending_valuation_deliveries} delivery
                        {balance.data.pending_valuation_deliveries === 1
                          ? ' is'
                          : 'ies are'}{' '}
                        still awaiting valuation and cannot be paid against yet.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
              <Field label="Amount" htmlFor="amount" required>
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

            <div>
              <span className="flex items-center gap-1 text-sm font-medium text-stone-700">
                Method
                <span className="text-danger" aria-hidden="true">
                  *
                </span>
              </span>
              <div className="mt-1.5 grid grid-cols-3 gap-2">
                {METHODS.map((m) => {
                  const selected = method === m.value
                  return (
                    <button
                      key={m.value}
                      type="button"
                      onClick={() => setMethod(m.value)}
                      className={cn(
                        'rounded-lg border px-3 py-3 text-sm font-medium transition-colors',
                        selected
                          ? 'border-primary-500 bg-primary-soft/70 text-primary-ink ring-1 ring-primary-500/20'
                          : 'border-border bg-card text-stone-700 hover:border-primary-300 hover:bg-primary-soft/30',
                      )}
                    >
                      {m.label}
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="border-t border-border/60 pt-5">
              <div className="space-y-4">
                <Field label="Reference" htmlFor="reference">
                  <TextInput
                    id="reference"
                    value={reference}
                    onChange={(e) => setReference(e.target.value)}
                    placeholder="e.g. MPESA code, bank ref, cash voucher"
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
              to="/payments"
              className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-900"
            >
              Cancel
            </Link>
            <Button type="submit" variant="primary" disabled={create.isPending}>
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Banknote className="h-4 w-4" />
              )}
              {create.isPending ? 'Recording…' : 'Record payment'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </div>
  )
}
