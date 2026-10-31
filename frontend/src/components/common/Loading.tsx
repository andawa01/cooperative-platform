/**
 * Loading and error affordances.
 *
 * A spinner alone reads as "nothing is happening". Skeletons and labelled
 * states tell a clerk what to expect, which matters on a slow rural connection.
 */
import { AlertCircle, Loader2, RefreshCw } from 'lucide-react'

import { cn } from '@/lib/utils'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-16 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin text-primary-500" />
      {label}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton-shimmer h-3', className)} />
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-danger/20 bg-danger-soft p-4 text-sm">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-danger" />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-danger-ink">Something went wrong</p>
        <p className="mt-1 break-words text-danger-ink/85">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-danger/25 bg-card px-2.5 py-1 text-xs font-medium text-danger-ink transition-colors hover:bg-danger-soft"
          >
            <RefreshCw className="h-3 w-3" />
            Try again
          </button>
        )}
      </div>
    </div>
  )
}
