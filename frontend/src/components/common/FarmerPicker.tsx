import { useEffect, useMemo, useState } from 'react'
import { Check, Search, UserRound } from 'lucide-react'

import { Avatar } from '@/components/common/Avatar'
import { useFarmers } from '@/hooks/useFarmers'
import type { Farmer } from '@/types/api'

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

  const results = useMemo(() => data?.items ?? [], [data])

  return (
    <div>
      <span className="flex items-center gap-1 text-sm font-medium text-stone-700">
        Farmer
        {required && (
          <span className="text-danger" aria-hidden="true">
            *
          </span>
        )}
      </span>

      {value ? (
        <div className="mt-1.5 flex items-center gap-3 rounded-lg border border-border bg-card p-2.5 shadow-xs">
          <Avatar first={value.first_name} last={value.last_name} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-foreground">
              {value.first_name} {value.last_name}
            </div>
            <div className="truncate text-xs text-muted-foreground tabular-nums">
              {value.phone}
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              onChange(null)
              setQuery('')
            }}
            className="rounded-md px-2 py-1 text-xs font-medium text-primary-ink transition-colors hover:bg-primary-soft"
          >
            Change
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="mt-1.5 flex w-full items-center gap-3 rounded-lg border border-dashed border-stone-300 bg-card px-3 py-3 text-left transition-colors hover:border-primary-400 hover:bg-primary-soft/40"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-stone-100 text-stone-400">
            <UserRound className="h-4 w-4" />
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-medium text-stone-700">
              Select a farmer
            </span>
            <span className="block text-xs text-muted-foreground">
              Search by name or phone number
            </span>
          </span>
        </button>
      )}

      {open && !value && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Select farmer"
          className="fixed inset-0 z-40 flex items-end justify-center bg-black/40 p-0 backdrop-blur-sm sm:items-center sm:p-4"
          onClick={() => setOpen(false)}
        >
          <div
            className="animate-in fade-in slide-in-from-bottom-4 flex max-h-[85vh] w-full max-w-md flex-col rounded-t-2xl bg-card shadow-lift duration-200 sm:rounded-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border/70 px-5 py-3.5">
              <h3 className="text-sm font-semibold text-foreground">
                Select farmer
              </h3>
              <button
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-stone-100 hover:text-foreground"
              >
                Close
              </button>
            </div>

            <div className="px-5 py-3">
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-stone-400" />
                <input
                  type="search"
                  autoFocus
                  placeholder="Search by name or phone"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="h-10 w-full rounded-lg border border-input bg-card pr-3 pl-9 text-[15px] shadow-xs transition-[border-color,box-shadow] placeholder:text-stone-400 focus:border-primary-500 focus:ring-4 focus:ring-primary-500/12 focus:outline-none"
                />
              </div>
            </div>

            <div className="min-h-24 flex-1 overflow-y-auto px-2 pb-3">
              {isLoading && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Searching…
                </p>
              )}
              {!isLoading && results.length === 0 && (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  No active farmers match “{query}”.
                </p>
              )}
              {results.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => {
                    onChange(f)
                    setOpen(false)
                  }}
                  className="group flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-stone-50"
                >
                  <Avatar first={f.first_name} last={f.last_name} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-foreground">
                      {f.first_name} {f.last_name}
                    </div>
                    <div className="truncate text-xs text-muted-foreground tabular-nums">
                      {f.phone}
                    </div>
                  </div>
                  <Check className="h-4 w-4 shrink-0 text-primary-ink opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
