/**
 * CSV export button.
 *
 * Exporting is an async request, not a navigation, so it needs its own
 * pending state and its own error surface — a failed export that silently
 * does nothing is the worst possible outcome for the person closing the
 * month's books.
 */
import { useState } from 'react'
import { Download, Loader2 } from 'lucide-react'

import { downloadCsv } from '@/lib/csv'

import { Button } from './Button'

export function ExportButton({
  path,
  params,
  label = 'Export CSV',
  className,
}: {
  path: string
  params?: Record<string, string | number | boolean | undefined>
  label?: string
  className?: string
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleClick = async () => {
    setPending(true)
    setError(null)
    try {
      await downloadCsv(path, params)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setPending(false)
    }
  }

  return (
    <div className={className}>
      {error && (
        <span role="alert" className="mr-2 text-xs text-danger-ink">
          {error}
        </span>
      )}
      <Button size="sm" onClick={handleClick} disabled={pending}>
        {pending ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Download className="h-3.5 w-3.5" />
        )}
        {pending ? 'Exporting…' : label}
      </Button>
    </div>
  )
}
