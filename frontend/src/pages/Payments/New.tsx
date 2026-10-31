import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Info } from 'lucide-react'

import { FarmerPicker } from '@/components/common/FarmerPicker'
import { ApiError } from '@/lib/api'
import { useCreatePayment } from '@/hooks/usePayments'
import { useFarmer, useFarmerBalance } from '@/hooks/useFarmers'
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
  const idempotencyKey = useMemo(
    () => `web-${crypto.randomUUID()}`,
    [],
  )

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
    <div className="p-4 md:p-6">
      <Link
        to="/payments"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to payments
      </Link>

      <h1 className="text-2xl font-semibold text-gray-900">Record payment</h1>
      <p className="mt-1 text-sm text-gray-600">
        The system will allocate this payment against the farmer's oldest
        unpaid deliveries (FIFO). Any excess becomes credit on account.
      </p>

      <form
        onSubmit={onSubmit}
        className="mt-6 max-w-xl space-y-5 rounded-lg border border-gray-200 bg-white p-5"
      >
        <FarmerPicker value={farmer} onChange={setFarmer} required />

        {farmer && balance.data && (
          <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm">
            <div className="flex items-start gap-2">
              <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-600" />
              <div className="space-y-1 text-blue-900">
                <div>
                  Outstanding debt:{' '}
                  <span className="font-semibold">
                    {formatMoney(balance.data.outstanding_debt, balance.data.currency)}
                  </span>
                </div>
                {Number(balance.data.available_credit) > 0 && (
                  <div>
                    Available credit:{' '}
                    <span className="font-semibold">
                      {formatMoney(balance.data.available_credit, balance.data.currency)}
                    </span>
                  </div>
                )}
                {balance.data.pending_valuation_deliveries > 0 && (
                  <div className="text-xs text-blue-800">
                    Note: {balance.data.pending_valuation_deliveries} delivery
                    {balance.data.pending_valuation_deliveries === 1 ? ' is' : 'ies are'}{' '}
                    still awaiting valuation. They cannot be paid against yet.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Amount <span className="ml-0.5 text-red-500">*</span>
            </label>
            <input
              type="number"
              inputMode="decimal"
              step="0.0001"
              min="0"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-3 text-lg font-medium shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
              placeholder="0.00"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">
              Currency
            </label>
            <select
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="mt-1 block h-[52px] rounded-md border border-gray-300 bg-white px-3 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            >
              <option value="KES">KES</option>
              <option value="UGX">UGX</option>
              <option value="TZS">TZS</option>
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Method <span className="ml-0.5 text-red-500">*</span>
          </label>
          <div className="mt-1 grid grid-cols-3 gap-2">
            {METHODS.map((m) => {
              const selected = method === m.value
              return (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setMethod(m.value)}
                  className={
                    'rounded-md border px-3 py-3 text-sm font-medium transition ' +
                    (selected
                      ? 'border-primary-500 bg-primary-50 text-primary-800'
                      : 'border-gray-300 bg-white text-gray-700 hover:border-primary-400')
                  }
                >
                  {m.label}
                </button>
              )
            })}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Reference
          </label>
          <input
            type="text"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            placeholder="e.g. MPESA code, bank ref, cash voucher"
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Notes
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-base shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-3 pt-1">
          <button
            type="submit"
            disabled={create.isPending}
            className="flex-1 rounded-md bg-primary-600 px-4 py-3 text-base font-medium text-white transition hover:bg-primary-700 disabled:opacity-60 sm:flex-none sm:px-6"
          >
            {create.isPending ? 'Recording…' : 'Record payment'}
          </button>
          <Link
            to="/payments"
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-base font-medium text-gray-700 hover:bg-gray-50 sm:py-2 sm:text-sm"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}