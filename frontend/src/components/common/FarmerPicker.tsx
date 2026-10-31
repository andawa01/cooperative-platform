import { useEffect, useState } from 'react'

import { useFarmers } from '@/hooks/useFarmers'
import type { Farmer } from '@/types/api'
import { cn } from '@/lib/utils'

export function FarmerPicker({
  value,
  onChange,
  required,
}: {
  value: Farmer | null
  onChange: (farmer: Farmer | null) => void
  required?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 250)
    return () => clearTimeout(t)
  }, [query])

  const { data, isLoading } = useFarmers(
    { search: debounced || undefined, limit: 20, status: 'active' },
    { enabled: open },
  )

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">
        Farmer
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>

      {value ? (
        <div className="mt-1 flex items-center justify-between rounded-md border border-gray-300 bg-white px-3 py-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-gray-900">
              {value.first_name} {value.last_name}
            </div>
            <div className="truncate text-xs text-gray-500">{value.phone}</div>
          </div>
          <button
            type="button"
            onClick={() => {
              onChange(null)
              setQuery('')
            }}
            className="ml-2 text-xs font-medium text-primary-600 hover:text-primary-700"
          >
            Change
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-1 w-full rounded-md border border-dashed border-gray-300 bg-white px-3 py-3 text-left text-sm text-gray-500 hover:border-primary-400 hover:bg-primary-50/40"
        >
          Tap to select a farmer…
        </button>
      )}

      {open && !value && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-30 flex items-end justify-center bg-black/30 sm:items-center"
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-t-xl bg-white p-4 shadow-lg sm:rounded-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-base font-semibold text-gray-900">
                Select farmer
              </h3>
              <button
                onClick={() => setOpen(false)}
                className="text-sm text-gray-500 hover:text-gray-800"
              >
                Close
              </button>
            </div>

            <input
              type="search"
              autoFocus
              placeholder="Search by name or phone"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-base focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
            />

            <div className="mt-3 max-h-80 overflow-y-auto">
              {isLoading && (
                <p className="py-4 text-center text-sm text-gray-500">Searching…</p>
              )}
              {data?.items.length === 0 && (
                <p className="py-4 text-center text-sm text-gray-500">
                  No farmers found
                </p>
              )}
              {data?.items.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    onChange(f)
                    setOpen(false)
                  }}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 rounded-md px-3 py-3 text-left',
                    'hover:bg-gray-50',
                  )}
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-gray-900">
                      {f.first_name} {f.last_name}
                    </div>
                    <div className="truncate text-xs text-gray-500">{f.phone}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}