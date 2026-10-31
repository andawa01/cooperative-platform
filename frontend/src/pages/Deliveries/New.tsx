import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { FarmerPicker } from '@/components/common/FarmerPicker'
import { ApiError } from '@/lib/api'
import { useCreateDelivery } from '@/hooks/useDeliveries'
import { useFarmer } from '@/hooks/useFarmers'
import { useProduceLines } from '@/hooks/useProduceLines'
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
    if (!Number.isFinite(q) || q <= 0) return setError('Quantity must be a positive number.')

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
    <div className="p-4 md:p-6">
      <Link
        to="/deliveries"
        className="mb-4 inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to deliveries
      </Link>

      <h1 className="text-2xl font-semibold text-gray-900">Record delivery</h1>
      <p className="mt-1 text-sm text-gray-600">
        Use the local time the produce was received.
      </p>

      <form
        onSubmit={onSubmit}
        className="mt-6 max-w-xl space-y-5 rounded-lg border border-gray-200 bg-white p-5"
      >
        <FarmerPicker value={farmer} onChange={setFarmer} required />

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Produce line
            <span className="ml-0.5 text-red-500">*</span>
          </label>
          {produceLines.isLoading && (
            <p className="mt-2 text-sm text-gray-500">Loading produce lines…</p>
          )}
          {produceLines.error && (
            <p className="mt-2 text-sm text-red-600">Failed to load produce lines.</p>
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
                    className={
                      'flex flex-col items-start gap-0.5 rounded-md border px-3 py-3 text-left transition ' +
                      (selected
                        ? 'border-primary-500 bg-primary-50 text-primary-800'
                        : 'border-gray-300 bg-white text-gray-700 hover:border-primary-400')
                    }
                  >
                    <span className="text-sm font-medium">{l.name}</span>
                    <span className="text-xs text-gray-500">per {l.unit}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Quantity
            {selectedLine && (
              <span className="ml-1 font-normal text-gray-500">
                ({selectedLine.unit})
              </span>
            )}
            <span className="ml-0.5 text-red-500">*</span>
          </label>
          <input
            type="number"
            inputMode="decimal"
            step="0.0001"
            min="0"
            required
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-3 text-lg font-medium shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            placeholder="0"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Collection point / location
          </label>
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="Optional"
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
            {create.isPending ? 'Recording…' : 'Record delivery'}
          </button>
          <Link
            to="/deliveries"
            className="rounded-md border border-gray-300 bg-white px-4 py-3 text-base font-medium text-gray-700 hover:bg-gray-50 sm:py-2 sm:text-sm"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  )
}